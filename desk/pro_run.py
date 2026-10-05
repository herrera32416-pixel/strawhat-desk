"""NBA + NHL daily entry point (.github/workflows/pro.yml). INFO ONLY: writes docs/data/nhl.json and docs/data/nba.json,
never touches the board, ledger or picks. Odds: <= 4 credits per sport per CT day via desk/pro_lines.py."""
import datetime as dt, traceback
from zoneinfo import ZoneInfo


def main():
    from . import nhl_run, nba_run
    for name, mod in (("NHL", nhl_run), ("NBA", nba_run)):
        try:
            out, notes = mod.main()
            print(f"{name}: {len(out['games'])} games; " + " | ".join(notes))
        except Exception:
            print(f"{name} error"); traceback.print_exc()
    print("done", dt.datetime.now(ZoneInfo("America/Chicago")).isoformat(timespec="minutes"))


if __name__ == "__main__":
    main()
