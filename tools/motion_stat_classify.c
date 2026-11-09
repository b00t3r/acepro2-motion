/* Offline only: status 3 was observed for one missing card-root file.
 * Call only with a separately verified, stable parent directory. The complete
 * native error semantics and behavior during I/O faults remain unverified.
 * This classifier alone must not authorize deletion of source files.
 */
int motion_stat_candidate_classify(int result, unsigned int detail) {
    if (result == 0 && detail == 0) return 1;
    if (result == 2 && detail == 3) return 0;
    return -1;
}
