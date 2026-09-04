"""Knockout bracket generation: sizing, seed placement, and BYE handling.

Pure and framework-agnostic, like the round-robin service — no Django
imports, operates on plain hashable participant identifiers, fully
unit-testable in isolation.

Key distinction that the implementation must get right: a BYE (auto-
advance with no match played) is a Round-1-only concept, arising purely
from padding the participant count up to a power of two. From Round 2
onward, a slot may already know its participant (because that participant
won a Round-1 bye) while the other slot is still pending an actual match
result — that is an ordinary future match, never an auto-advance, even
when both slots happen to already be known (e.g. two Round-1 byes feeding
the same Round-2 match: both participants are known, but they still have
to play it).
"""

import random
from dataclasses import dataclass, field
from typing import Any, Hashable, Optional


def next_power_of_two(n: int) -> int:
    if n < 1:
        return 1
    power = 1
    while power < n:
        power *= 2
    return power


def seed_positions(bracket_size: int) -> list[int]:
    """Standard recursive bracket-seeding sequence.

    Returns a list of length bracket_size where element i is the seed rank
    (1-indexed, 1 = strongest) placed in bracket slot i, guaranteeing seed 1
    and 2 can only meet in the final, seeds 1-4 only from the semifinal on,
    and so on.
    """
    if bracket_size < 1 or (bracket_size & (bracket_size - 1)) != 0:
        raise ValueError("bracket_size must be a power of 2")

    sequence = [1]
    size = 1
    while size < bracket_size:
        sequence = [value for s in sequence for value in (s, 2 * size + 1 - s)]
        size *= 2
    return sequence


@dataclass(frozen=True)
class BracketMatch:
    round_number: int
    slot: int
    participant_a: Optional[Any]
    participant_b: Optional[Any]
    is_bye: bool = False
    bye_winner: Optional[Any] = None
    is_third_place: bool = False


@dataclass(frozen=True)
class KnockoutBracket:
    bracket_size: int
    rounds: int
    matches: list[BracketMatch] = field(default_factory=list)
    has_third_place_match: bool = False


def generate_knockout_bracket(
    participants: list[Hashable],
    *,
    seeded: bool = True,
    third_place: bool = False,
    random_seed: int | None = None,
) -> KnockoutBracket:
    """Generate a knockout bracket for the given participants.

    Args:
        participants: participant identifiers. If seeded=True, list order
            is the seed order (participants[0] is seed 1, the strongest).
            If seeded=False, this is a random draw: order is shuffled
            (deterministically, if random_seed is given) before placement.
        seeded: whether to use standard seed placement or a random draw.
        third_place: whether to reserve a third-place match between the
            two semifinal losers (only possible when a semifinal exists,
            i.e. at least 2 rounds).
        random_seed: seed for the deterministic shuffle used when
            seeded=False. Ignored when seeded=True.

    Returns:
        A KnockoutBracket with every round's matches. Round 1 matches carry
        real participants (or a BYE, auto-resolved). Later rounds carry a
        participant only where it is already known from a Round-1 bye;
        otherwise both slots are None pending the actual match result.
    """
    n = len(participants)
    if n != len(set(participants)):
        raise ValueError("participants must not contain duplicates")
    if n < 2:
        return KnockoutBracket(bracket_size=0, rounds=0, matches=[], has_third_place_match=False)

    items = list(participants)
    if not seeded and random_seed is not None:
        random.Random(random_seed).shuffle(items)

    bracket_size = next_power_of_two(n)
    total_rounds = bracket_size.bit_length() - 1

    if seeded:
        positions = seed_positions(bracket_size)
        slot_participant = [items[rank - 1] if rank <= n else None for rank in positions]
    else:
        slot_participant = [items[slot] if slot < n else None for slot in range(bracket_size)]

    matches: list[BracketMatch] = []
    round1_winners: list[Optional[Any]] = []
    num_r1_matches = bracket_size // 2

    for i in range(num_r1_matches):
        a, b = slot_participant[2 * i], slot_participant[2 * i + 1]
        is_bye = (a is None) != (b is None)
        bye_winner = a if (is_bye and a is not None) else (b if (is_bye and b is not None) else None)
        matches.append(BracketMatch(round_number=1, slot=i, participant_a=a, participant_b=b, is_bye=is_bye, bye_winner=bye_winner))
        round1_winners.append(bye_winner)

    prev_round_known = round1_winners
    current_size = num_r1_matches
    for round_number in range(2, total_rounds + 1):
        next_size = current_size // 2
        next_known: list[Optional[Any]] = []
        for i in range(next_size):
            a, b = prev_round_known[2 * i], prev_round_known[2 * i + 1]
            # Never an auto-advance bye, even if both sides are already
            # known (e.g. two Round-1 byes feeding the same match) — see
            # module docstring.
            matches.append(BracketMatch(round_number=round_number, slot=i, participant_a=a, participant_b=b))
            next_known.append(None)
        prev_round_known = next_known
        current_size = next_size

    has_third_place = third_place and total_rounds >= 2
    if has_third_place:
        matches.append(
            BracketMatch(
                round_number=total_rounds,
                slot=-1,
                participant_a=None,
                participant_b=None,
                is_third_place=True,
            )
        )

    return KnockoutBracket(bracket_size=bracket_size, rounds=total_rounds, matches=matches, has_third_place_match=has_third_place)
