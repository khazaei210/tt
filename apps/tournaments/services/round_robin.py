"""Round-robin scheduling via the standard circle method.

Pure, deterministic, and framework-agnostic: this module has no Django
imports and knows nothing about Participant/Match models. It operates on
plain hashable identifiers (typically Participant primary keys) so it can
be unit-tested in isolation and reused wherever a round-robin schedule is
needed.

Algorithm: fix the first participant, arrange the rest in a circle, and
rotate the circle by one position each round. This is the standard
"polygon method" for round-robin scheduling and guarantees every pair of
participants meets exactly once per leg, with no duplicates.
"""

import random
from dataclasses import dataclass, field
from typing import Any, Hashable

BYE = object()  # sentinel for "no opponent this round" (odd participant count)


@dataclass(frozen=True)
class Fixture:
    round_number: int
    participant_a: Any
    participant_b: Any


@dataclass(frozen=True)
class RoundRobinSchedule:
    rounds: int
    fixtures: list[Fixture] = field(default_factory=list)
    byes: dict[int, Any] = field(default_factory=dict)  # round_number -> participant sitting out


def generate_round_robin(
    participants: list[Hashable],
    *,
    legs: int = 1,
    seed: int | None = None,
) -> RoundRobinSchedule:
    """Generate a round-robin schedule for the given participants.

    Args:
        participants: participant identifiers. Order matters only when no
            seed is given (it is preserved as-is, e.g. seed order supplied
            by the caller); with a seed, the order is deterministically
            shuffled first.
        legs: 1 for single round robin (each pair meets once), 2 for
            double round robin (each pair meets twice, fixtures reversed
            for the second leg).
        seed: if given, participant order is shuffled deterministically
            with this seed before scheduling, so the same seed always
            reproduces the same schedule. If omitted, no shuffling occurs.

    Returns:
        A RoundRobinSchedule with every fixture and, for odd participant
        counts, which participant has a bye in each round.

    Raises:
        ValueError: on duplicate participants or legs < 1.
    """
    if legs < 1:
        raise ValueError("legs must be at least 1")

    items = list(participants)
    if len(items) != len(set(items)):
        raise ValueError("participants must not contain duplicates")

    if len(items) < 2:
        return RoundRobinSchedule(rounds=0, fixtures=[], byes={})

    if seed is not None:
        rng = random.Random(seed)
        rng.shuffle(items)

    if len(items) % 2 == 1:
        items = items + [BYE]

    n = len(items)
    num_rounds = n - 1
    fixed = items[0]
    rotating = items[1:]

    fixtures: list[Fixture] = []
    byes: dict[int, Any] = {}

    for round_index in range(num_rounds):
        round_number = round_index + 1
        arr = [fixed] + rotating
        for i in range(n // 2):
            a, b = arr[i], arr[n - 1 - i]
            if a is BYE:
                byes[round_number] = b
            elif b is BYE:
                byes[round_number] = a
            else:
                fixtures.append(Fixture(round_number, a, b))
        rotating = [rotating[-1]] + rotating[:-1]

    if legs > 1:
        all_fixtures = list(fixtures)
        all_byes = dict(byes)
        for leg in range(1, legs):
            offset = leg * num_rounds
            for f in fixtures:
                all_fixtures.append(Fixture(f.round_number + offset, f.participant_b, f.participant_a))
            for round_number, participant in byes.items():
                all_byes[round_number + offset] = participant
        fixtures = all_fixtures
        byes = all_byes
        num_rounds *= legs

    return RoundRobinSchedule(rounds=num_rounds, fixtures=fixtures, byes=byes)
