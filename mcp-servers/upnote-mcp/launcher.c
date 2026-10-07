/*
 * Starts the UpNote MCP server so a Full Disk Access grant survives upgrades.
 *
 * The Claude desktop app launches MCP servers as their own "responsible" process, so macOS
 * checks the launched binary, not Claude, before letting it read UpNote's
 * container. Homebrew's uv and Python are ad-hoc signed, so a grant on them is
 * tied to one exact build and is lost on every brew upgrade. This launcher
 * never changes, so a grant on it holds. It must stay alive as the parent:
 * exec'ing uv would make uv the binary macOS checks again.
 *
 * The command is fixed at build time rather than taken from argv, so the
 * grant cannot be borrowed to run anything else.
 *
 * Build: see README.md, "Full Disk Access".
 */
#include <signal.h>
#include <spawn.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/wait.h>

#ifndef UV_PATH
#define UV_PATH "/opt/homebrew/bin/uv"
#endif

extern char **environ;

static pid_t child;

static void forward(int sig) {
    if (child > 0)
        kill(child, sig);
}

int main(void) {
    const char *home = getenv("HOME");
    if (!home) {
        fprintf(stderr, "upnote-mcp-launcher: HOME is not set\n");
        return 1;
    }
    char script[4096];
    snprintf(script, sizeof script, "%s/.claude/mcp-servers/upnote-mcp/server.py", home);

    char *args[] = {UV_PATH, "run", "--script", script, NULL};
    int err = posix_spawn(&child, UV_PATH, NULL, NULL, args, environ);
    if (err) {
        fprintf(stderr, "upnote-mcp-launcher: cannot start %s: %s\n", UV_PATH, strerror(err));
        return 1;
    }

    signal(SIGTERM, forward);
    signal(SIGINT, forward);
    signal(SIGHUP, forward);

    int status;
    while (waitpid(child, &status, 0) < 0) {
    }
    if (WIFEXITED(status))
        return WEXITSTATUS(status);
    return 128 + WTERMSIG(status);
}
