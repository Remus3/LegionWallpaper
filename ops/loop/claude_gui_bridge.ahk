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
;   control\ahk_mode.txt   = "dry" (type into Notepad LW-LOOP-DRYRUN) or "live"
;   control\target_pid.txt = PID of the dedicated Claude window titled "Image"
; Live mode with a missing/empty target_pid.txt ABORTS the bridge outright.
; Exits when control\STOP appears.

CTL := "C:\LegionWallpaper\ops\loop\control"
READY := CTL "\gemini.ready"
TYPED := CTL "\typed.flag"
STOPF := CTL "\STOP"
MODEF := CTL "\ahk_mode.txt"
PIDF := CTL "\target_pid.txt"
DRY_TITLE := "LW-LOOP-DRYRUN"
LINE_PAUSE := 1500

LogMsg(s) {
    global CTL
    FileAppend(FormatTime(, "yyyy-MM-dd HH:mm:ss") " " s "`n", CTL "\ahk_bridge.log")
}

Target() {
    global MODEF, PIDF, DRY_TITLE
    mode := FileExist(MODEF) ? Trim(FileRead(MODEF)) : "live"
    if (mode = "dry")
        return DRY_TITLE
    pid := FileExist(PIDF) ? Trim(FileRead(PIDF)) : ""
    if (pid = "") {
        LogMsg("ABORT: live mode with no target_pid.txt (pid-only policy, no title fallback)")
        ExitApp
    }
    return "ahk_pid " pid
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
            } else {
                SendText(lineText)
            }
            Sleep 350
            Send("{Enter}")
            typed += 1
            Sleep LINE_PAUSE
        }
        FileDelete(READY)              ; READY consumed = the "typed" signal the controller waits on
        LogMsg("typed " typed " lines into [" win "]")
    }
    Sleep 1000
}
