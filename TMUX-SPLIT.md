tmux split cheat sheet — build a grid, then claim a console area
==============================================================

PREFIX is Ctrl-b. Press it, release, then the key.


1. THE SPLITS
-------------
  Ctrl-b %      split horizontally  → new pane BELOW     (makes ROWS)
  Ctrl-b "      split vertically    → new pane RIGHT    (makes COLUMNS)

  With the mouse on, click-drag the divider to resize freely.


2. THE MATRIX — how many splits for an R x C grid
--------------------------------------------------
  A grid of R rows x C columns holds R*C panes, and every split adds
  exactly one pane. So:

         C=1   C=2   C=3   C=4   C=5
    R=1   0     1     2     3     4
    R=2   1     3     5     7     9
    R=3   2     5     8    11    14
    R=4   3     7    11    15    19

  splits needed = (R * C) - 1

  Worked example, 4 rows x 3 columns = 12 panes = 11 splits:

  THE ORDER IS THE WHOLE TRICK. Aim every split at ONE pane, never at
  the grid:
    - Ctrl-b %  x3        aim at the same pane  -> 4 rows
    - Ctrl-b "  x2        aim at the same pane  -> 3 columns
    - Ctrl-b "  x2        aim at the pane from the previous split
    - Ctrl-b "  x2        same again
    - Ctrl-b "  x2        same again
    - Ctrl-b "  x2        same again

  In words: rows first, then walk down the rows adding columns. Each
  vertical split aims at the pane you just made, so it lands in the row
  you are working on.

  What goes wrong if you ignore that: aiming a % at a pane you have
  already split makes ragged rows, because each split only divides the
  pane you aimed at. The result is rows of 6/5/12/24 cells instead of four
  even ones, and "no space for new pane" once they get too thin.


3. MOVING BETWEEN SQUARES
-------------------------
  Ctrl-b  Left / Right / Up / Down    move one pane
  Ctrl-b  n / p                        next / previous pane
  Ctrl-b  q                            close the focused pane
  Ctrl-b  x                            detach the pane into its own window

  The arrow keys are the reliable ones. If they stop responding, the
  prefix may not have registered — press and release Ctrl-b again.


4. RESIZING
-----------
  Ctrl-b Alt-Arrow     resize the focused pane by 1 cell
  Ctrl-b ,             enter resize MODE, then Arrow keys resize
                       (q / w / h / l also work; Escape or Enter to finish)

  Without a prefix, in resize mode: q=up w=down h=left l=right
  Ctrl-b R             enter verbose resize mode with a live readout


5. CLAIMING AN AREA AS ONE CONSOLE
----------------------------------
Three different things, pick by how permanent you want it:

  a) ZOOM  (reversible, usually what you want)
       Ctrl-b z
     The focused pane fills the whole window; the others are hidden but
     still alive. Press Ctrl-b z again to get the grid back.
     This is "I want this square to be my console right now".

  b) JOIN / MERGE  (permanent)
       join-pane -s <source> -t <destination>
     <source> is folded into <destination>. With -d they become two
     stacked layers you cycle with "join-pane -d -s .. -t ..".
     Caveat: joining collapses the grid, so keep a spare session
     (tmux new-window) before you do it.

  c) BREAK OUT  (moves it elsewhere, does not merge)
       Ctrl-b x        detach the pane into its own window
       Ctrl-b b        break the pane into a new window below
       Ctrl-b s then Arrow   swap the focused pane with its neighbour


6. MAKING A CONSOLE FROM SCRATCH
--------------------------------
  Ctrl-b c            new window (a blank shell)
  Ctrl-b ,            rename the window (so you can find it later)
  Ctrl-b $            rename the SESSION
  Ctrl-b 0-9          jump to window 0-9

  A pane's command is fixed at creation, so to turn an existing square
  into the FoveAI console you either replace it, or from inside it run:
      foveai            the FoveAI menu console


7. IF SOMETHING GOES WRONG
--------------------------
  Ctrl-b d            DETACH — panes keep running, nothing is lost
  tmux ls             list sessions
  tmux attach -t NAME re-attach
  tmux kill-session -t NAME   kill it and start over

  Detach is the safe move. Almost nothing is ever lost by detaching.


8. SCRIPTING IT (if you want the grid without the keypresses)
--------------------------------------------------------------
  From the shell, not from a tmux prompt:

    tmux new-session -d -s demo -x 200 -y 50
    tmux split-window -t demo -h -l 20 "exec sleep 999"   # new pane RIGHT
    tmux split-window -t demo -b -l 20 "exec sleep 999"   # new pane BELOW

  TRAP: the flags must come BEFORE -l. Writing
      tmux split-window -h -l 20 -d "cmd"
  makes tmux read "-d" as the COMMAND to run, so the split silently does
  nothing and the pane you expected never appears.

  Layout strings exist but are fiddly; skip them.