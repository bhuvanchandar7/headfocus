// HeadFocus.app launcher.
//
// Starts headfocus.py as a child process so macOS attributes Camera and
// Accessibility permission to HeadFocus.app instead of the Python binary.
// HEADFOCUS_DIR (the repo folder) is set at build time by setup.sh.
#include <signal.h>
#include <spawn.h>
#include <stdio.h>
#include <sys/wait.h>
#include <unistd.h>

#ifndef HEADFOCUS_DIR
#error "Build with -DHEADFOCUS_DIR=\"/path/to/headfocus\" (setup.sh does this)"
#endif

extern char **environ;
static pid_t child = 0;
static void forward(int sig) { if (child > 0) kill(child, sig); }

int main(void) {
    char *args[] = {HEADFOCUS_DIR "/.venv/bin/python", "-u",
                    HEADFOCUS_DIR "/headfocus.py", "run", "-q", NULL};
    signal(SIGTERM, forward);
    signal(SIGINT, forward);
    if (posix_spawn(&child, args[0], NULL, NULL, args, environ) != 0) {
        perror("HeadFocus: could not start Python (run setup.sh again)");
        return 1;
    }
    int status;
    while (waitpid(child, &status, 0) < 0) {}
    return WIFEXITED(status) ? WEXITSTATUS(status) : 1;
}
