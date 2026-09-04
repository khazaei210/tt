# Table Tennis Tournament Management System

## 1. Project Overview

This project is a production-quality, extensible Table Tennis Tournament Management System.

The system must support:

- Individual competitions
- Team competitions
- Doubles competitions
- Round-robin tournaments
- Knockout tournaments
- Group + knockout tournaments
- Tournament draws
- Seeding
- BYE handling
- Match scheduling
- Match management
- Live score entry
- Tournament standings
- Player rankings
- Ranking points
- Referee / scorekeeper operations
- Tournament administration
- Reports and statistics

The project must be designed as a reusable tournament management platform, not as a single-purpose CRUD application.

The core domain is tournament correctness: draw generation, scheduling, match results, standings, ranking and tournament progression.

---

# 2. Technology Stack

## Backend

- Python
- Django
- PostgreSQL

## Frontend

- Django Templates
- Tailwind CSS
- DaisyUI
- HTMX
- Alpine.js only when genuinely necessary

## Infrastructure

- Docker
- Docker Compose
- PostgreSQL
- Nginx when required

## Architecture

Use Django Full Stack architecture.

Do NOT introduce React, Vue, Angular, Next.js, or another SPA framework unless explicitly requested.

The frontend should be server-rendered using Django Templates, enhanced with HTMX where useful.

---

# 3. Development Environment

The application is developed on a remote Linux VPS.

VS Code connects to the VPS using Remote SSH.

Claude Code runs on the VPS inside the project repository.

All development commands should be designed to run in the VPS environment.

The preferred development environment is Dockerized.

Do not require PostgreSQL to be installed directly on the developer's local machine.

---

# 4. General Architecture Principles

Follow Django conventions and favor simple, maintainable architecture.

Use:

- Django ORM
- Django Forms / ModelForms
- Class Based Views where appropriate
- Function Based Views where simpler
- Template inheritance
- Reusable template components
- Service layer for complex business logic
- Domain-oriented Django applications

Complex tournament business logic must not live directly inside templates or views.

Tournament algorithms should be implemented as independent, deterministic and testable services.

Avoid premature abstraction.

Do not introduce design patterns merely for the sake of using patterns.

---

# 5. Suggested Django Applications

Start with a structure similar to:

apps/
    core/
    accounts/
    players/
    teams/
    tournaments/
    competitions/
    matches/
    rankings/
    venues/
    reports/

The structure may evolve if there is a strong architectural reason.

Do not create a separate Django app for every small feature.

---

# 6. Core Domain Concepts

Keep the following concepts separate:

- Tournament
- Competition
- CompetitionRule
- Participant
- Player
- Team
- DoublesPair
- Stage
- Group
- Round
- Draw
- Match
- MatchSet
- MatchResult
- Standing
- Ranking
- RankingEvent
- Venue
- Table

Do not create one giant model that represents all tournament concepts.

---

# 7. Participants

The tournament engine must operate on a generic Participant concept.

Supported participant types:

## Individual

One player represents one participant.

## Doubles

Two players represent one doubles participant/pair.

## Team

A team contains multiple players.

The draw, scheduling and match engines must work with participants instead of assuming that every participant is a single player.

---

# 8. Tournament Structure

A Tournament may contain one or more Competitions.

A Competition defines:

- participant type
- tournament format
- rules
- stages
- ranking/standings behavior

Examples:

- Men's Singles
- Women's Singles
- Men's Doubles
- Mixed Doubles
- Team Championship

A competition may contain multiple stages.

Examples:

- Group Stage
- Round of 32
- Round of 16
- Quarter Final
- Semi Final
- Final
- Third Place

---

# 9. Tournament Formats

The system must support at least:

## Round Robin

Support:

- Single round robin
- Double round robin
- Even participant counts
- Odd participant counts
- BYE handling
- No duplicate pairings
- Standard circle-method scheduling

## Knockout

Support:

- Round of 64
- Round of 32
- Round of 16
- Quarter Final
- Semi Final
- Final
- Third-place match
- BYE
- Non-power-of-two participant counts

## Group + Knockout

Support:

- Multiple groups
- Group scheduling
- Group standings
- Qualification rules
- Automatic advancement
- Knockout bracket generation

---

# 10. Draw and Seeding

The draw engine must support:

- Random draw
- Seeded draw
- Manual draw
- BYE
- Seed positions
- Reproducible randomization when requested
- Draw preview
- Draw locking

A locked draw must not be modified silently.

Changes to a locked draw require explicit administrator authorization.

The system should preserve the generated draw and its state.

---

# 11. Tournament Algorithms

Tournament generation must be deterministic and testable.

Recommended services include:

- TournamentDrawService
- RoundRobinScheduler
- KnockoutBracketService
- GroupStageService
- StandingsService
- RankingService
- MatchResultService
- TournamentProgressionService

Do not implement tournament algorithms directly inside views.

Avoid random behavior that cannot be reproduced or tested.

---

# 12. Round Robin Requirements

For round robin scheduling:

- Every participant must play the required number of opponents.
- No duplicate pairings may be generated.
- BYE must be supported for odd participant counts.
- Single round robin must produce each pairing once.
- Double round robin must produce each pairing twice.
- Match order should be deterministic when a seed/randomization value is supplied.
- Scheduling must be testable independently of Django views.

---

# 13. Knockout Requirements

The knockout engine must:

- Determine the required bracket size.
- Generate BYEs when necessary.
- Respect seeds.
- Generate subsequent rounds.
- Propagate winners to the next round.
- Support third-place matches when configured.
- Prevent impossible bracket states.
- Preserve bracket structure after draw locking.

---

# 14. Match Domain

A Match represents a competition between two Participants.

A Match should support concepts such as:

- competition
- stage
- round
- group
- bracket position
- participant A
- participant B
- winner
- scheduled time
- start time
- end time
- table
- referee
- scorekeeper
- status

Possible statuses include:

- scheduled
- ready
- live
- completed
- cancelled
- postponed
- walkover
- retired
- default

Do not rely only on a final numeric score to determine match state.

---

# 15. Match Sets and Scoring

A Match consists of multiple MatchSets.

Example:

Set 1: 11-8
Set 2: 9-11
Set 3: 11-7
Set 4: 11-9

Final:

Player A wins 3-1.

The system must preserve individual set scores.

Do not store only the final match score.

Score validation must be performed server-side.

---

# 16. Competition Rules

Competition rules must be configurable.

Support concepts such as:

- Best of 3
- Best of 5
- Best of 7
- Points per set
- Win by 2
- Deuce rules
- Deciding set rules
- Maximum set score where applicable

Do not hard-code rules such as "11 points" or "best of 5" throughout the application.

Business rules must be represented explicitly.

---

# 17. Standings

Round-robin standings should support:

- Played
- Wins
- Losses
- Match points
- Sets won
- Sets lost
- Set difference
- Points scored
- Points conceded
- Point difference

Tie-break rules must be configurable.

Potential tie-breakers:

1. Match points
2. Head-to-head
3. Set difference
4. Point difference
5. Points scored

Do not assume that one ranking/tie-break rule applies to every competition.

---

# 18. Head-to-Head

Head-to-head calculations must be carefully designed.

For tied participants:

- Determine the applicable tied group.
- Apply the competition's configured tie-break sequence.
- Avoid incorrectly using a single head-to-head result when three or more participants are tied.
- Add tests for two-way and multi-way ties.

---

# 19. Player Ranking

Tournament standings and global player ranking are different concepts.

Tournament standings determine position within one competition.

Player ranking determines a player's ranking across multiple competitions.

Keep these concepts separate.

The ranking system should be extensible so that future algorithms can be introduced without rewriting tournament standings.

Potential ranking data:

- ranking points
- previous ranking
- current ranking
- ranking change
- tournaments played
- wins
- losses
- ranking events

---

# 20. Tournament Management

Authorized tournament managers should be able to:

- Create tournaments
- Configure tournaments
- Create competitions
- Register participants
- Manage players
- Manage teams
- Configure formats
- Configure competition rules
- Seed participants
- Generate draws
- Review draws
- Lock draws
- Generate schedules
- Assign tables
- Assign referees
- Manage matches
- Correct scores
- Cancel matches
- Postpone matches
- Publish results
- View standings
- View rankings
- Export reports

---

# 21. Referee / Scorekeeper

Provide a focused match management interface.

Authorized users should be able to:

- Open assigned match
- Start match
- Enter set scores
- Correct set scores
- Complete match
- Record winner
- Record walkover
- Record retirement
- Record default

The UI should be optimized for fast data entry.

Avoid unnecessary navigation during live scoring.

---

# 22. Live Scoring

Use HTMX for live score updates where appropriate.

Avoid WebSockets unless actual requirements justify the added complexity.

Live scoring may update:

- Current set
- Match score
- Match status
- Winner
- Match clock where needed
- Standings after match completion

All authoritative score calculations must happen server-side.

---

# 23. UI / UX

Use:

- Tailwind CSS
- DaisyUI
- Django Templates
- HTMX
- Responsive design
- RTL support
- Persian-friendly typography
- Accessible forms
- Clear status indicators
- Mobile-friendly score entry

The primary interface should support Persian.

Use Django internationalization for user-facing strings.

Do not hard-code user-facing text when translation support is appropriate.

---

# 24. DaisyUI

Use DaisyUI components consistently.

Prefer reusable UI components for:

- buttons
- cards
- badges
- tables
- modals
- alerts
- forms
- tabs
- dropdowns
- navigation
- breadcrumbs
- pagination
- dialogs

Maintain a coherent design system.

Do not mix several unrelated CSS frameworks.

---

# 25. Dashboard

Provide dashboards for different roles.

Tournament Manager dashboard:

- Active tournaments
- Upcoming matches
- Live matches
- Completed matches
- Participant count
- Table utilization
- Current standings
- Tournament progress

Scorekeeper / Referee dashboard:

- Assigned matches
- Current live match
- Pending matches
- Fast score entry

Player dashboard:

- Upcoming matches
- Match history
- Tournament participation
- Ranking
- Ranking changes

---

# 26. Roles and Permissions

At minimum consider:

- Super Admin
- Tournament Admin
- Tournament Manager
- Referee
- Scorekeeper
- Player
- Viewer

Use Django authentication and authorization.

Never rely only on frontend visibility to protect an operation.

All sensitive actions must be authorized server-side.

---

# 27. Security

Follow Django security best practices.

Never:

- expose secrets in Git
- commit real .env files
- disable CSRF protection
- disable authentication
- trust client-side score calculations
- allow unauthorized result modifications

Use environment variables for secrets.

Provide `.env.example`.

---

# 28. Database Design

Use PostgreSQL.

Use:

- ForeignKey
- OneToOneField
- ManyToManyField
- UniqueConstraint
- CheckConstraint
- indexes

Use database constraints for important invariants where practical.

Do not add indexes blindly.

For performance-sensitive queries consider:

- select_related()
- prefetch_related()
- annotations
- aggregation
- database-side calculations

Avoid N+1 queries.

---

# 29. Docker

Development must run through Docker Compose.

At minimum:

- web: Django
- db: PostgreSQL

Future services may include:

- redis
- celery
- celery-beat

Do not require PostgreSQL to run directly on the VPS host.

Prefer official, maintained base images.

---

# 30. Configuration

Use environment variables for:

- SECRET_KEY
- DEBUG
- DATABASE_URL or database settings
- ALLOWED_HOSTS
- CSRF settings
- email settings
- external integrations

Never commit production credentials.

---

# 31. Testing

Significant business rules require automated tests.

Especially test:

- round-robin generation
- single round robin
- double round robin
- odd participant counts
- BYE handling
- duplicate pairing prevention
- seeded draw
- random draw
- knockout bracket generation
- non-power-of-two brackets
- score validation
- winner calculation
- standings
- head-to-head
- multi-way tie-breaks
- ranking calculation
- tournament progression
- authorization
- locked draw behavior

Do not consider tournament engine features complete without tests.

---

# 32. Performance

Performance matters because a tournament can contain many participants and matches.

Pay attention to:

- N+1 queries
- standings calculation
- bracket rendering
- dashboard queries
- ranking queries
- match lists
- statistics

Optimize based on evidence.

Do not perform premature optimization.

---

# 33. Data Integrity and Audit

Tournament results are important business data.

Completed matches must not be silently overwritten.

Important changes should be traceable.

Score corrections should preserve an audit trail where practical.

Do not silently modify historical tournament results.

---

# 34. Git Workflow

Never work directly on `main` for feature development.

Use branches such as:

- claude/feature-round-robin
- claude/feature-knockout
- claude/feature-live-scoring
- claude/feature-ranking

Before committing:

1. Run relevant tests.
2. Run Django checks.
3. Verify migrations.
4. Review `git diff`.
5. Check for secrets.
6. Check generated files.

Do not automatically commit or push unless explicitly requested.

---

# 35. Claude Code Behavior

Before modifying the project:

1. Inspect the existing architecture.
2. Read relevant files.
3. Identify dependencies.
4. Identify risks.
5. For complex changes, propose an implementation plan first.
6. Implement the smallest clean solution.
7. Run relevant tests.
8. Run Django checks.
9. Review the diff.
10. Clearly report what changed.

Do not rewrite large portions of the project unnecessarily.

Do not introduce dependencies without explaining why.

Do not delete existing functionality unless explicitly requested.

Do not assume unspecified business rules.

---

# 36. Database Safety

NEVER execute destructive commands against production databases.

Never execute the following against production without explicit authorization:

- DROP DATABASE
- DROP TABLE
- TRUNCATE
- destructive migrations
- bulk deletion
- mass updates

Development databases may be recreated when explicitly requested.

---

# 37. Code Quality

Prefer:

- readable code
- explicit names
- small cohesive functions
- domain services
- reusable template components
- type hints where useful
- meaningful tests
- clear error handling

Avoid:

- giant views
- giant models
- duplicated business logic
- magic numbers
- hard-coded tournament rules
- unnecessary abstractions
- premature optimization

---

# 38. Development Process

For each feature:

1. Understand the requirement.
2. Inspect relevant code.
3. Identify domain implications.
4. Propose architecture if needed.
5. Implement models.
6. Create migrations.
7. Implement services.
8. Implement forms.
9. Implement views.
10. Implement templates.
11. Add HTMX interactions where useful.
12. Write tests.
13. Run tests.
14. Run Django checks.
15. Review Git diff.
16. Report implementation and remaining issues.

---

# 39. Important Domain Principle

This is not a generic CRUD application.

The tournament engine is the core domain.

Prioritize correctness of:

- draws
- scheduling
- match results
- standings
- rankings
- tournament progression

over adding large numbers of UI features.

Tournament algorithms must be independently testable from Django views and templates.

---

# 40. Initial Development Roadmap

Build incrementally.

Phase 1:
- Docker
- Django
- PostgreSQL
- Tailwind
- DaisyUI
- HTMX
- Basic configuration

Phase 2:
- Accounts
- Players
- Teams
- Doubles pairs

Phase 3:
- Tournament
- Competition
- Participant
- Rules
- Stage
- Group

Phase 4:
- Round-robin engine
- Scheduling
- Standings

Phase 5:
- Knockout engine
- Seeding
- BYE
- Brackets

Phase 6:
- Match
- MatchSet
- MatchResult
- Score validation

Phase 7:
- Tournament progression
- Ranking
- Ranking points

Phase 8:
- Tournament administration dashboard

Phase 9:
- Referee / scorekeeper interface
- Live scoring
- HTMX interactions

Phase 10:
- Reports
- Statistics
- Export
- Audit/history
- Production hardening

Do not implement everything in one step.

Each phase must leave the application in a working state.

---

# 41. Current Priority

Before implementing the domain models, fully analyze the requirements and design the domain model.

Pay particular attention to:

Tournament
    -> Competition
        -> Stage
            -> Group / Round
                -> Draw
                    -> Match
                        -> MatchSet

and:

Participant
    -> Individual Player
    -> Doubles Pair
    -> Team

The domain model must allow the same tournament engine to operate across all supported participant types and formats.

Do not start by generating a large amount of code.

First establish a sound architecture and domain model.
