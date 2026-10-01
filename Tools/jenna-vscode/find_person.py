with open(
    r"c:\Users\danie\program\LUMAX\Tools\jenna-vscode\src\webview\chat.html",
    "r",
    encoding="utf-8",
) as f:
    for num, line in enumerate(f, 1):
        if "personBottomBtn" in line:
            print(f"{num}: {line.strip()}")
