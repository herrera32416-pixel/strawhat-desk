"""TEASERS role helpers: payouts and ticket math (DK & Bovada NFL regular-season 6-pt table, verified Oct 2 2026:
ats.io DK table and bovada.lv help page both list 2:-120, 3:+160/+150, 4:+260, 5:+400, 6:+600)."""
DK6 = {1: None, 2: -120, 3: 160, 4: 260, 5: 400, 6: 600}
# Standard 6-pt NFL teaser payouts used for 4-, 5- and 6-leg tickets (same table; ties reduce the ticket one size down).
# Break-even:            ticket            per leg (independent legs)
#   4 legs +260 (3.60x)  27.78%            72.60%
#   5 legs +400 (5.00x)  20.00%            72.48%
#   6 legs +600 (7.00x)  14.29%            72.30%
MIN_LEG_P = 0.723   # every teaser leg (conditional on no push) must be >= the 6-leg break-even; 4/5-leg tickets must also clear EV > 0


def dec(a):
    return 1 + (a / 100 if a > 0 else 100 / -a)


def breakeven_leg(n=6, payout=None):
    payout = DK6[n] if payout is None else payout
    return (1 / dec(payout)) ** (1 / n)


def breakeven_ticket(n=6):
    return 1 / dec(DK6[n])


def settle(results, table=DK6):
    """results: list of 'W'/'L'/'P'. DK: ties removed, ticket reduces. Returns units on 1u."""
    if "L" in results:
        return -1.0
    k = results.count("W")
    if k == 0:
        return 0.0
    if k == 1:  # all others pushed: graded as a straight bet at -110 approximately -> treat as no action (conservative)
        return 0.0
    return dec(table[k]) - 1


def ticket_prob(legs):
    """legs: list of (p_win, p_push). Independence assumed. Returns (P(win ticket), EV per 1u at DK table)."""
    import itertools
    n = len(legs)
    ev = 0.0; pw = 0.0
    # enumerate win/push states (losses kill the ticket)
    for states in itertools.product((0, 1), repeat=n):  # 1 = win, 0 = push
        p = 1.0
        for (w, pu), s in zip(legs, states):
            p *= w if s else pu
        k = sum(states)
        if k >= 2:
            ev += p * (dec(DK6[k]) - 1); pw += p
    p_any_loss = 1 - sum(
        __import__("math").prod((w if s else pu) for (w, pu), s in zip(legs, st))
        for st in itertools.product((0, 1), repeat=n))
    ev -= p_any_loss
    return pw, ev
