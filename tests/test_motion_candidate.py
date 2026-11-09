"""Execute the packaged ARM64 save hook with mocked camera filesystem APIs."""
import hashlib
import json
import re
import struct
import sys
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
import lz4.frame
from unicorn import Uc, UC_ARCH_ARM64, UC_MODE_ARM, UC_HOOK_CODE
from unicorn.arm64_const import *

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT/'tools'))
from build_motion_candidate import BASE, CAVE, CAVE_END, HOOK, SOURCE, SOURCE_SHA, OUT
from build_usb_name_candidate import unpack_package, USB_OFFSETS
from make_motion_photo import jpeg_end, package
from build_clean_motion_photo import capture_timestamp_ms


class Machine:
    def __init__(self, jpeg=None, lrv=None, name='LIV_20261027_200749_030.jpg', live=1,
                 status=0, timestamp=1401, fail=None, existing=None, native_format=False,
                 image_data=None):
        self.uc = Uc(UC_ARCH_ARM64, UC_MODE_ARM)
        self.image = (image_data if image_data is not None else lz4.frame.decompress(unpack_package(
            next(OUT.glob('Insta360*.bin')).read_bytes())['parts'][0]['payload']))
        self.uc.mem_map(BASE, (len(self.image)+4095)&~4095)
        self.uc.mem_write(BASE, self.image)
        self.uc.mem_map(0x50000000, 0x20000)
        self.uc.mem_map(0x70000000, 0x20000)
        self.uc.mem_map(0x71000000, 0x1000)
        self.uc.mem_map(0x1262e000, 0x1000)
        self.uc.mem_map(0x1264f000, 0x1000)
        self.uc.mem_write(0x1262e904, struct.pack('<I', live))
        self.uc.mem_write(0x1264f320, struct.pack('<Q', timestamp))
        self.uc.reg_write(UC_ARM64_REG_CPACR_EL1, 3 << 20)
        self.uc.mem_write(0x71000000, b'\x1f\x20\x03\xd5')
        self.uc.mem_write(0x50000000, ('C:\\DCIM\\Camera01\\'+name).encode()+b'\0')
        self.path = 'C:\\DCIM\\Camera01\\'+name
        # Small, structurally valid baseline JPEG with a thumbnail EOI inside APP2.
        self.jpeg = jpeg if jpeg is not None else (b'\xff\xd8\xff\xe1\x00\x08Exif\0\0'
            + b'\xff\xe2\x00\x06\xff\xd8\xff\xd9' + b'\xff\xc0\x00\x02'
            + b'\xff\xda\x00\x02' + b'A'*1010 + b'\xff\x00\xd9B\xff\xd9' + b'vendor metadata')
        self.lrv = lrv if lrv is not None else b'\0\0\0\x18ftypavc1'+b'B'*5000
        self.files = {self.path: self.jpeg, self.path[:-4]+'.lrv': self.lrv}
        self.files.update(existing or {})
        self.originals = dict(self.files)
        self.handles, self.events = {}, []
        self.live, self.timestamp, self.fail = live, timestamp, fail
        self.open_count, self.write_count, self.close_count = 0, 0, 0
        self.allocated = False
        self.regs = [UC_ARM64_REG_X0, UC_ARM64_REG_X1, UC_ARM64_REG_X2,
                     UC_ARM64_REG_X3, UC_ARM64_REG_X4, UC_ARM64_REG_X5,
                     UC_ARM64_REG_X6, UC_ARM64_REG_X7]
        funcs = {0x26a860:self.open, 0x26a8a0:self.close, 0x26a960:self.read,
                 0x26a9c0:self.write, 0x26aa20:self.seek, 0x26aa40:self.tell,
                 0x26aba0:self.rename, 0x25dee0:self.alloc, 0x25e5e0:self.free,
                 0x2639a0:self.format, 0x403820:lambda: live,
                 0x403920:lambda: timestamp}
        for address, fn in funcs.items():
            if native_format and address in (0x2639a0, 0x403820, 0x403920):
                continue
            self.uc.hook_add(UC_HOOK_CODE, self.callback(fn), begin=address, end=address)
        for i in range(19):
            self.uc.reg_write(UC_ARM64_REG_X0+i, 0xA000+i)
        self.uc.reg_write(UC_ARM64_REG_X20, 0x50000000)
        self.uc.reg_write(UC_ARM64_REG_X24, status)
        self.uc.reg_write(UC_ARM64_REG_SP, 0x70010000)
        self.uc.reg_write(UC_ARM64_REG_X30, 0x71000000)
        self.uc.reg_write(UC_ARM64_REG_NZCV, 0xa0000000)
        self.uc.mem_write(0x70010088, struct.pack('<Q', 0x1122334455667788))

    def arg(self, i):
        return self.uc.reg_read(self.regs[i])

    def string(self, address):
        return bytes(self.uc.mem_read(address, 1024)).split(b'\0', 1)[0].decode()

    def callback(self, fn):
        def call(uc, address, size, _):
            result = fn()
            # A real callee may destroy every caller-saved GPR and flags.
            for i in range(19):
                uc.reg_write(UC_ARM64_REG_X0+i, 0xBAAD0000+i)
            uc.reg_write(UC_ARM64_REG_X0, int(result or 0) & ((1<<64)-1))
            uc.reg_write(UC_ARM64_REG_NZCV, 0x50000000)
            uc.reg_write(UC_ARM64_REG_PC, uc.reg_read(UC_ARM64_REG_X30))
        return call

    def open(self):
        path, mode, ptr = self.string(self.arg(0)), self.string(self.arg(1)), self.arg(2)
        self.events.append(('open', path, mode))
        if mode == 'rb':
            if path not in self.files or self.fail == 'missing_lrv' and path.endswith('.lrv'):
                self.uc.mem_write(ptr, b'\0'*8)
                return 1
        elif mode == 'wb':
            if path in self.originals or not path.endswith('.MP.tmp'):
                raise AssertionError('Attempt to overwrite original media')
            if self.fail == 'open_dest':
                return 1
            self.files[path] = bytearray()
        else:
            raise AssertionError('Unexpected open mode')
        handle = 0x80000000 + len(self.handles)*16
        self.handles[handle] = [path, mode, 0]
        self.uc.mem_write(ptr, struct.pack('<Q', handle))
        return 0

    def close(self):
        handle = self.arg(0)
        path = self.handles.pop(handle)[0]
        self.events.append(('close', path))
        return 1 if self.fail == 'close_dest' and path.endswith('.tmp') else 0

    def read(self):
        pointer, size, count, handle = [self.arg(i) for i in range(4)]
        path, mode, pos = self.handles[handle]
        data = self.files[path][pos:pos+size*count]
        if self.fail == 'read':
            data = data[:-1]
        self.uc.mem_write(pointer, bytes(data))
        self.handles[handle][2] += len(data)
        return len(data)//size

    def write(self):
        pointer, size, count, handle = [self.arg(i) for i in range(4)]
        path, mode, pos = self.handles[handle]
        if mode != 'wb':
            raise AssertionError('Writing input file')
        data = bytes(self.uc.mem_read(pointer, size*count))
        self.write_count += 1
        if self.fail == 'write' and self.write_count == 4:
            data = data[:-1]
        self.files[path].extend(data)
        self.handles[handle][2] += len(data)
        return len(data)//size

    def seek(self):
        handle, offset, origin = [self.arg(i) for i in range(3)]
        if self.fail == 'seek':
            return 1
        f = self.handles[handle]
        f[2] = offset + (len(self.files[f[0]]) if origin == 2 else 0)
        return 0

    def tell(self):
        self.uc.mem_write(self.arg(1), struct.pack('<Q', self.handles[self.arg(0)][2]))
        return 0

    def rename(self):
        src, dst = self.string(self.arg(0)), self.string(self.arg(1))
        if dst in self.files:
            raise AssertionError('Rename overwrites existing file')
        if self.fail == 'rename':
            return 1
        self.files[dst] = self.files.pop(src)
        self.events.append(('rename', src, dst))
        return 0

    def alloc(self):
        if self.fail == 'alloc':
            return 1
        assert self.arg(1) == 5120
        self.uc.mem_write(self.arg(0), struct.pack('<Q', 0x50002000))
        self.allocated = True
        return 0

    def free(self):
        assert self.arg(0) == 0x50002000
        self.allocated = False
        return 0

    def format(self):
        fmt = self.string(self.arg(2))
        if self.fail == 'format':
            return 1024
        values = iter([self.arg(3), self.arg(4), self.arg(5)])
        result = re.sub(r'%llu|%u', lambda _: str(next(values)), fmt).encode()
        self.uc.mem_write(self.arg(0), result+b'\0')
        return len(result)

    def run(self):
        self.uc.emu_start(HOOK, HOOK+4, timeout=30_000_000, count=80_000_000)
        assert self.uc.reg_read(UC_ARM64_REG_PC) == HOOK+4
        assert self.uc.reg_read(UC_ARM64_REG_SP) == 0x70010000
        assert self.uc.reg_read(UC_ARM64_REG_X0) == 0x1122334455667788
        assert self.uc.reg_read(UC_ARM64_REG_NZCV) == 0xa0000000
        for i in range(1, 19):
            assert self.uc.reg_read(UC_ARM64_REG_X0+i) == 0xA000+i
        assert self.uc.reg_read(UC_ARM64_REG_X20) == 0x50000000
        assert not self.handles and not self.allocated
        for path, before in self.originals.items():
            assert bytes(self.files[path]) == before
        return self.files.get(self.path[:-4]+'.MP.jpg')


class MotionCandidateTests(unittest.TestCase):
    def test_success_matches_phone_tested_packaging(self):
        m = Machine()
        output = m.run()
        video_start = len(output)-len(m.lrv)
        p = 4+int.from_bytes(output[4:6], 'big')
        n = int.from_bytes(output[p+2:p+4], 'big')
        self.assertEqual(output[:p]+output[p+n+2:video_start], m.jpeg)
        self.assertEqual(output[video_start:], m.lrv)
        root = ET.fromstring(output[p+4:p+n+2].split(b'\0', 1)[1])
        ns = '{http://ns.google.com/photos/1.0/camera/}'
        description = root.find('.//{http://www.w3.org/1999/02/22-rdf-syntax-ns#}Description')
        self.assertEqual(description.attrib[ns+'MotionPhotoPresentationTimestampUs'], '1401000')

    def test_actual_native_formatter_and_timestamp_getters(self):
        m = Machine(native_format=True)
        output = m.run()
        self.assertIsNotNone(output)
        self.assertIn(b'Camera:MotionPhotoPresentationTimestampUs="1401000"', output)

    def test_capture_timestamp_is_per_capture(self):
        m = Machine(timestamp=1334)
        self.assertIn(b'1334000', m.run())

    def test_native_output_from_real_doc_pair(self):
        jpg = (ROOT/'doc/LIV_20261027_200749_030.jpg').read_bytes()
        lrv = (ROOT/'doc/LIV_20261027_200749_030.lrv').read_bytes()
        m = Machine(jpeg=jpg, lrv=lrv, timestamp=capture_timestamp_ms(jpg))
        output = bytes(m.run())
        # Check actual metadata semantics, including APP1 order and payload bounds.
        p = 4+int.from_bytes(output[4:6], 'big')
        self.assertEqual(output[6:12], b'Exif\0\0')
        n = int.from_bytes(output[p+2:p+4], 'big')
        xml = output[p+4:p+2+n].split(b'\0', 1)[1]
        root = ET.fromstring(xml)
        items = root.findall('.//{http://ns.google.com/photos/1.0/container/}Item')
        ns = '{http://ns.google.com/photos/1.0/container/item/}'
        video_size = int(items[1].attrib[ns+'Length'])
        padding = int(items[0].attrib[ns+'Padding'])
        self.assertEqual(video_size, len(lrv))
        self.assertEqual(jpeg_end(output)+padding, len(output)-video_size)
        self.assertEqual(output[-video_size:], lrv)
        # Removing only inserted XMP recovers the entire original JPEG byte-for-byte.
        self.assertEqual(output[:p]+output[p+n+2:-video_size], jpg)
        (OUT/'Native_DocCapture_TrialM.MP.jpg').write_bytes(output)

    def test_errors_do_not_publish_jpg_or_change_inputs(self):
        for failure in ['missing_lrv', 'open_dest', 'read', 'write', 'seek', 'alloc',
                        'format', 'close_dest', 'rename']:
            with self.subTest(failure=failure):
                m = Machine(fail=failure)
                self.assertIsNone(m.run())

    def test_existing_output_and_temp_are_not_overwritten(self):
        for suffix in ['.MP.jpg', '.MP.tmp']:
            path = 'C:\\DCIM\\Camera01\\LIV_20261027_200749_030'+suffix
            m = Machine(existing={path: b'keep'})
            m.run()
            self.assertEqual(m.files[path], b'keep')
            self.assertFalse(any(e[0] == 'open' and e[2] == 'wb' for e in m.events))

    def test_not_livephoto_or_failed_capture_does_nothing(self):
        for kwargs in [{'live':0}, {'status':1}, {'name':'IMG_20261027_200749_030.jpg'},
                       {'name':'LIV_20261027_200749_030.mp4'}, {'timestamp':10001}]:
            with self.subTest(kwargs=kwargs):
                m = Machine(**kwargs)
                self.assertIsNone(m.run())

    def test_invalid_jpeg_does_not_publish(self):
        for jpg in [b'B'*2000, b'\xff\xd8\xff\xe1\xff\xff'+b'B'*2000,
                    b'\xff\xd8\xff\xe1\x00\x08Exif\0\0'+b'B'*2000]:
            m = Machine(jpeg=jpg)
            self.assertIsNone(m.run())

    def test_only_allowlisted_decoded_bytes_changed_from_v(self):
        source = SOURCE.read_bytes()
        self.assertEqual(hashlib.sha256(source).hexdigest(), SOURCE_SHA)
        before = lz4.frame.decompress(unpack_package(source)['parts'][0]['payload'])
        after = Machine().image
        allowed = set(range(CAVE-BASE, CAVE_END-BASE)) | set(range(HOOK-BASE, HOOK-BASE+4))
        for offset in USB_OFFSETS:
            allowed.add(offset+17)
        self.assertTrue(all(a == b or i in allowed for i, (a,b) in enumerate(zip(before, after))))
        self.assertEqual(len(before), len(after))


if __name__ == '__main__':
    unittest.main()
