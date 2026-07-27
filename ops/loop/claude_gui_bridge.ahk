#Requires AutoHotkey v2.0
#SingleInstance Force
SetTitleMatchMode 2
; gemini-headless-upgrade GUI bridge (the HANDS). The ONLY GUI actor.
; LW port of the RC bridge under the RC 81636382 collision contract:
; live targeting is PID-ONLY (no title fallback) - RC's launcher self-defers
; while any LegionWallpaper bridge is alive, and each repo's launcher kills
; only its own cmdline-scoped bridge instances.
; Polls control\gemini.ready; types its lines into the TARGET window; ack =
; deleting gemini.ready. Target is FILE-DRIVEN (config not code):
;   control\ahk_mode.txt    = "dry" (type into Notepad LW-LOOP-DRYRUN) or "live"
;   control\target_hwnd.txt = HWND of the Claude window titled "Image". ONE
;                             claude.exe process owns MULTIPLE project windows
;                             (Image/RC/...), so pid alone is AMBIGUOUS - the
;                             hwnd pins the exact window. target_pid.txt is
;                             informational only (launcher writes both).
; Live mode with a missing/empty target_hwnd.txt ABORTS the bridge outright.
; Exits when control\STOP appears.

CTL := "C:\LegionWallpaper\ops\loop\control"
READY := CTL "\gemini.ready"
TYPED := CTL "\typed.flag"
STOPF := CTL "\STOP"
MODEF := CTL "\ahk_mode.txt"
HWNDF := CTL "\target_hwnd.txt"
DRY_TITLE := "LW-LOOP-DRYRUN"
LINE_PAUSE := 1500
; Extra settle AFTER a /clear commits: the session reset repaints the TUI, and a
; follow-up slash-send at bare LINE_PAUSE raced it - /gemini-headless-upgrade could
; land mid-clear and get eaten (operator 2026-07-16).
CLEAR_PAUSE := 4000

LogMsg(s) {
    global CTL
    FileAppend(FormatTime(, "yyyy-MM-dd HH:mm:ss") " " s "`n", CTL "\ahk_bridge.log")
}

Target() {
    global MODEF, HWNDF, DRY_TITLE
    mode := FileExist(MODEF) ? Trim(FileRead(MODEF)) : "live"
    if (mode = "dry")
        return DRY_TITLE
    hwnd := FileExist(HWNDF) ? Trim(FileRead(HWNDF)) : ""
    if (hwnd = "") {
        LogMsg("ABORT: live mode with no target_hwnd.txt (hwnd-only policy, no title/pid fallback)")
        ExitApp
    }
    return "ahk_id " hwnd
}

LogMsg("ahk bridge start (LW)")
Loop {
    if FileExist(STOPF) {
        LogMsg("STOP seen, exit")
        ExitApp
    }
    if FileExist(READY) {
        content := FileRead(READY)
        lines := StrSplit(content, "`n", "`r")
        win := Target()
        if !WinExist(win) {
            LogMsg("target window not found: " win)
            Sleep 1500
            continue
        }
        WinActivate(win)
        WinWaitActive(win, , 5)
        Sleep 500
        typed := 0
        for idx, lineText in lines {
            if (idx = 1)                 ; skip CYCLE=n header
                continue
            if (Trim(lineText) = "")
                continue
            if (SubStr(lineText, 1, 1) = "/") {
                ; Slash-command line: commit the leading "/" on its own and pause so
                ; the Claude TUI slash-menu opens BEFORE the command word arrives.
                ; SendText of the whole short string raced that menu and the "/" landed
                ; AFTER the word ("clear/" not "/clear"), so /clear silently no-op'd and
                ; the session never reset (RC 2026-06-06). The leading-slash split forces
                ; the slash ahead of the word.
                SendText("/")
                Sleep 400
                SendText(SubStr(lineText, 2))
                ; Trailing space: with the command palette open, Enter is captured by the
                ; dropdown (no-op when nothing is highlighted) so a bare "/clear" never
                ; submits - observed idle-window at 2026-07-17 00:03. A space after the
                ; token closes the palette; Enter then submits and the command parses at
                ; submit time. Lines with args already carry spaces and always submitted.
                SendText(" ")
            } else {
                SendText(lineText)
            }
            Sleep 350
            Send("{Enter}")
            ; SECOND Enter (operator-observed 2026-07-26: text landed in the composer
            ; but was never submitted). Same failure class as the slash-palette scar
            ; above - something transient (autocomplete, paste-mode, a hint row) eats
            ; the first Enter, so the directive sits typed-but-unsent and the whole
            ; cycle stalls until the deadline. Sending a second Enter is SAFE because
            ; if the first one DID submit, the composer is now empty and Enter on an
            ; empty composer is a no-op. Cheap insurance against a silent stall.
            Sleep 250
            Send("{Enter}")
            typed += 1
            Sleep LINE_PAUSE
            if (Trim(lineText) = "/clear")
                Sleep CLEAR_PAUSE
        }
        FileDelete(READY)              ; READY consumed = the "typed" signal the controller waits on
        LogMsg("typed " typed " lines into [" win "]")
    }
    Sleep 1000
}
