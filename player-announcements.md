# SHCC Storm — Player Announcement System

A working spec for producing player headshot announcements (captaincy, signings, milestones, awards, debuts, farewells) that look like a coherent professional set, using the kind of source photos a suburban club actually has.

**How to use it.** Upload a player photo, paste the Brief Block (§10) with the fields filled in, and point at this file. The system decides the layout from the photo quality tier (§4), not from taste — that is what keeps a season of announcements looking like one set.

---

## 1. Non-negotiables

These five rules produce more of the "professional" look than anything else in this document. If time is short, do only these.

1. **Every photo gets the same grade.** The grade is the brand, not the photo. A series is recognisable because the treatment is identical, even when the source photos came from six different phones.
2. **Two type families, maximum.** One heavy condensed display face, one clean geometric sans. No brush script, no grunge/distressed faces, no third family.
3. **A shout and a whisper, nothing between.** The headline is enormous; everything else is small caps with wide tracking. Delete the mid-sized tier — group that content instead.
4. **All secondary information lives in one block.** One container, one alignment axis, hairline rules inside it. Never scatter date/venue/grade/stat across the canvas.
5. **Elements either bleed off the edge or respect the margin exactly.** Never "almost" at the edge. The logo is the one exception — it is never cropped.

---

## 2. Brand tokens

### Colour

| Token | Hex | Use |
|---|---|---|
| `storm-teal` | `#14A5B5` | Sole accent. Headlines, rules, the bolt, one word per graphic. |
| `storm-teal-deep` | `#0E6B78` | Duotone midtones, hover/secondary states, panel borders. |
| `storm-teal-tint` | `#1F4A52` | Panel fills, dividers, background shapes. Present, never loud. |
| `charcoal` | `#1A1A2A` | The field. Default background. Navy-cast, never pure black. |
| `ink` | `#0D0D16` | Deepest shadows, duotone black point, footer bars. |
| `cool-grey` | `#8A9196` | Tertiary text only — captions, de-emphasised labels. |
| `white` | `#FFFFFF` | Primary information. |

**Resolve the teal before the first build.** The style guide says `#00C9B0`; the graphics currently shipping are running closer to `#14A5B5` (cyan-leaning) and `#2E8F9B` (duller, greener). Pick one, set it as the token, and enforce it. Nothing reads as unprofessional faster than a brand colour that drifts between posts.

**Rules.** Three values only on any single graphic: field, white, teal. `cool-grey` and `storm-teal-tint` exist to extend hierarchy, not to add colour. Never introduce a second hue — no gold, no red, no green, not for sponsors, not for "Player of the Month."

### Type

| Role | Face | Notes |
|---|---|---|
| Display | **Anton**, Bebas Neue, or Archivo Black | Heavy condensed grotesque. Free, web-safe, Druk-adjacent. Used for the one big word and the surname. |
| Text | **Poppins** (already in club use) or Montserrat | Everything else. SemiBold for names, Medium for detail, Regular for body. |

Banned: the grunge/distressed condensed face, the heavy brush script, and the italic serif currently appearing on club event graphics. The logo keeps its own jagged wordmark because badges are exempt — that is the only place that face appears.

### Logo

- Primary lockup (figure + wordmark) for large use, minimum 260px wide at 1080 canvas.
- Icon-only (figure + bolt, wordmark removed, simplified) below that.
- **Never crop the logo.** Bleed the type off the edge; never the mark. A cropped headline still reads; a cropped logo just looks broken.
- Mono white or mono teal version when placing over photography.
- Clear space on all sides = the height of the bolt in the mark.

### The bolt

The highest-value asset in the brand. Use it at every scale:

- Full-bleed background element (low contrast, `storm-teal-tint`, under 15% opacity).
- Divider between blocks.
- Bullet separator in footer and metadata lines — `SYDENHAM ⚡ HILLSIDE ⚡ CRICKET CLUB`.
- Corner furniture at 16–20px, `cool-grey`, barely visible.

Micro-detail that advertises the grid is what makes a layout read as engineered rather than assembled.

---

## 3. Announcement types

Each type has a fixed eyebrow, a fixed display word, and a fixed set of detail fields. Do not invent new wording per player — the repetition is what makes them a series.

| Type | Eyebrow (small caps) | Display word | Detail fields |
|---|---|---|---|
| Captain appointment | `2026/27 SEASON` | **CAPTAIN** | Grade, previous role, seasons at club |
| Vice-captain | `2026/27 SEASON` | **VICE-CAPTAIN** | Same |
| New signing | `NEW FOR 2026/27` | **SIGNED** | Previous club, role (bat/bowl/all-rounder/keeper), grade |
| Re-signing | `ONE CLUB, ONE STORM` | **RE-SIGNED** | Seasons at club, grade |
| Debut | `SENIOR DEBUT` | **DEBUT** | Grade, opposition, date |
| Milestone | `CLUB MILESTONE` | **100 GAMES** / **1000 RUNS** / **100 WICKETS** | Career span, grade(s), the raw stat |
| Player of the match | `ROUND 7` | **PLAYER OF THE MATCH** | Figures, opposition, grade |
| Award winner | `2025/26 AWARDS` | **B&F WINNER** (etc.) | Award name, votes/figures, grade |
| Coach / committee | `2026/27 SEASON` | **COACH** / **COMMITTEE** | Position title, tenure |
| Farewell | `THANK YOU` | **FAREWELL** | Seasons, games, headline career numbers |

**Copy limits.** Eyebrow ≤ 24 characters. Display word ≤ 14 characters (it must fit one line edge-to-edge in a condensed face). Surname ≤ 12 characters before it needs to shrink. Each detail field ≤ 28 characters. If a field will not fit, cut the field — never shrink the headline.

**Cricket formatting conventions.** Figures as `3/24`, not "3 for 24". Not-out as `47*`. Grades as `1st XI`, `2nd XI`, `3rd XI`, `Under 16s`. Player names as `Given Surname` on first appearance, surname alone in the display setting.

---

## 4. Source photo triage

**This is the step that decides the layout.** Assess the uploaded photo against the table below before choosing anything else. Be honest about the tier — forcing a Tier C photo into a Tier A layout is the most common failure, and no amount of grading rescues it.

| Tier | Test | Layout allowed |
|---|---|---|
| **A — Hero** | Face occupies ≥ 600px across the eyes. Sharp. Player looking at or near camera. Eyes visible (no sunglasses, no helmet grille shadow). Background separable from subject. | T1, T2, T3 |
| **B — Workable** | Face 300–600px. Slightly soft, or harsh sun, or busy background, or cap shadow across eyes, or shot from mid-distance. Subject is still clearly identifiable. | T2, T3 |
| **C — Weak** | Face under 300px, or cropped out of a team photo, or screenshot-compressed, or heavy motion blur, or face largely obscured (helmet, sunglasses, turned away). | T3 (small panel), T4 |
| **D — Unusable** | No usable photo at all, or the player cannot be identified from it, or a third party is unavoidably in frame. | T4 or T5 |

### Diagnostics to run on every upload

- **Resolution at the crop you actually want.** Cropping tight to a face does not add pixels — it removes them. If the final crop would place fewer than ~600px across the face in a T1 hero, drop a tier. Do not upscale and hope.
- **Compression artifacts.** Blockiness around the collar, hairline, and jaw edge. Screenshots from social media almost always have these. They survive every treatment except halftone.
- **Colour cast.** Indoor nets go green-yellow under fluorescents; midday sun goes blue in the shadows. The duotone grade removes this entirely, which is one of the main reasons it exists.
- **Kit inconsistency.** Some players in whites, some in coloured kit, some in a training tee. Duotone flattens the difference; a full-colour treatment will not.
- **Blown highlights.** Midday sun on white cricket kit clips to pure white and cannot be recovered. Plan for it: let the kit go to paper-white and let the field carry the contrast, rather than fighting for detail that is not there.
- **Third parties in frame.** Crop them out or mask them out entirely. Never publish a graphic with an unidentified person in the background.

---

## 5. Photo treatment recipes

Apply in order. The same recipe runs on every photo in a series regardless of tier — that consistency is the whole point.

### 5.1 The house grade (mandatory, every photo)

1. **Desaturate fully.** Take the photo to greyscale first. This kills white-balance variance, mixed kit colours, and skin-tone inconsistency between phone cameras in one move.
2. **Duotone map.** Black point → `ink` `#0D0D16`. White point → `#FFFFFF`. Midtones pulled slightly toward `storm-teal-deep` `#0E6B78`. The result reads as "brand-coloured photography" rather than "a photo on a coloured background."
3. **Crush the shadows.** Lift the black point until background clutter disappears into the field. A messy clubroom or a chain-link fence turns into flat dark. This is the single most effective background fix available without a clean mask.
4. **Push local contrast on the face only.** Keeps the subject reading after the shadows are crushed.
5. **Grain, always.** Fine monochrome grain at 4–8% across the entire canvas — over the photo, over the type, over the flat fields. It unifies the masked subject with the background so nothing looks pasted on, and it gives low-resolution photos a reason to be soft.

### 5.2 Halftone (Tier B and C)

Coarse dot or line screen at 4–8px dot pitch. This is the fix for compression artifacts and softness: it replaces accidental noise with intentional texture. A halftoned 400px face reads as a deliberate print aesthetic; the same face untreated reads as a bad photo. Apply the screen to the photo layer only, then the global grain over everything.

### 5.3 Cut-out on flat field (Tier A, and Tier B with a clean edge)

Mask the subject, place on a flat `charcoal` field. Hard-edged masks on flat colour hide a great deal — there is no background texture for the edge to fail against.

- Hair edges are where low-resolution masks break. Mitigate by placing the subject over the dark field (not a light one) so any halo is invisible, or by adding a 2px `charcoal` stroke on the mask edge.
- If the mask is failing at the hairline after two attempts, abandon the cut-out and use a gradient scrim (§5.4) instead. A visible bad mask is worse than a visible background.

### 5.4 Gradient scrim (Tier B fallback)

Rather than masking, place a `charcoal`-to-transparent gradient over the lower 45% and a vignette around the edges. Background clutter darkens away, and the scrim becomes the surface the type sits on. Cheap, fast, and it never fails the way a mask does.

### 5.5 Shape masking (Tier C)

Confine the photo to a hard geometric crop — circle, arch, or rounded rectangle — at a size where the resolution holds. A small, sharp, well-framed photo reads as intentional; a large soft one reads as a mistake. The shape does the design work and the photo just fills it.

### 5.6 Silhouette (Tier D, and rescue for Tier C)

Reduce the subject to a high-contrast two-tone silhouette filled with `storm-teal` or a bolt texture, on `charcoal`. Detail disappears, so resolution stops mattering entirely. Works especially well for a batter in a stance or a bowler in delivery, where the outline alone carries the sport. This is a legitimate design choice, not a compromise — pair it with a type-dominant layout and it sits comfortably in the same series as the hero portraits.

### 5.7 Crop rules

- **Eye line on the upper third.** Not centred. Centring a face vertically is the default that professional sets avoid.
- **Crop the top of the head.** Confidently, not by 5px. Headroom above a subject reads as an unedited snapshot.
- **Crop to the shoulders or wider — never mid-neck.** A neck-only crop looks like a passport photo.
- **Off-centre horizontally** so the headline has a side to live on.
- If the player is wearing sunglasses or a helmet, do not fight it — go to a T3 or T4 layout where the face is not doing the work.

---

## 6. Layout templates

All specs at **1080 × 1350px** (4:5). Outer margin **72px**, respected exactly by everything except deliberate full bleeds.

### T1 — Hero Portrait *(Tier A only)*

Type-dominant with the figure cutting through it.

```
┌──────────────────────────────────────┐
│  ⚡                            [logo] │  ← 72px margin, icon-only logo 88px
│                                      │
│   2026/27 SEASON                     │  ← eyebrow, 22px caps, tracking 200, teal
│                                      │
│   ██████ CAPTAIN ██████              │  ← display, 190px cap height, bleeds both edges
│         ╱╲                           │
│        ╱  ╲   ← cut-out subject      │  ← subject occludes the headline
│       ╱    ╲     overlaps type       │
│      │ face │                        │
│      │      │                        │
│                                      │
│   SURNAME                            │  ← 110px, display face, white
│   Given name                         │  ← 38px, Poppins SemiBold, teal
│   ┌────────────────────────────┐     │
│   │ 1ST XI · ALL-ROUNDER       │     │  ← detail module, 20px caps, tracking 180
│   │ 6TH SEASON AT THE CLUB     │     │     hairline rules between rows
│   └────────────────────────────┘     │
│  ⚡ ONE CLUB, ONE STORM            ⚡ │  ← footer, 16px caps, tracking 220, cool-grey
└──────────────────────────────────────┘
```

The display word bleeds past both margins. The subject sits in front of it, obscuring 25–40% of the letterforms. Partially hidden words still read — the brain completes them — and the occlusion is what creates depth on a flat canvas.

### T2 — Split Field *(Tier A or B)*

Hard horizontal division at 55–60% down the canvas. Everything above is flat `charcoal` carrying the type on a single centred axis; everything below is the photograph, bleeding to all three lower edges. The split line is a 3px `storm-teal` rule running full width.

Forgiving, because the photo only has to work as a bottom-of-frame band and the messy parts crop away.

### T3 — Panel Portrait *(Tier B or C)*

Type-dominant, photo confined. The photo occupies a shape-masked panel (circle at 420px, or an arch at 420 × 560px) on one side; the entire opposite side carries the type stack on a single left-aligned axis. Background is flat `charcoal` with a low-opacity bolt at 12% opacity behind the type.

This is the workhorse. Most club photos are Tier B, and this template makes a mediocre photo look like a deliberate editorial choice.

### T4 — Silhouette / Type-Only *(Tier C or D)*

No usable portrait. The display word fills the upper half at 240px cap height. A silhouetted figure — the player if there is any usable outline, otherwise a generic batter or bowler silhouette from the club asset set — sits in `storm-teal-tint` behind the type, bleeding off the bottom edge. Name and detail module bottom-left.

Use the same silhouette across all Tier D announcements in a season. It becomes a recognisable device rather than an obvious gap-filler.

### T5 — Squad Strip *(multiple players)*

For leadership groups, life members, or a full captains announcement. Three to five shape-masked portraits in a horizontal strip at equal size, all on the same baseline, all under the identical grade. Names in a single row beneath, all caps, tracked 180, with hairline vertical rules between them.

Equal treatment across every player in the strip, even if one photo is far better than the others. Grade to the weakest photo in the set — a set is only as consistent as its worst member.

---

## 7. Type scale

At 1080 × 1350. Scale proportionally for other sizes.

| Role | Size (cap height) | Face / weight | Tracking | Case |
|---|---|---|---|---|
| Display word | 190–240px | Anton | −20 to −40 | UPPER |
| Surname | 100–130px | Anton | −10 | UPPER |
| Given name | 34–44px | Poppins SemiBold | 0 | Title |
| Eyebrow | 20–24px | Poppins Medium | +200 | UPPER |
| Detail fields | 20–24px | Poppins Medium | +180 | UPPER |
| Body / quote | 26–30px | Poppins Regular | 0 | Sentence |
| Footer / micro | 15–18px | Poppins Medium | +220 | UPPER |

**The tracking relationship is inverse and it matters more than the sizes.** Big type tracked tight, small type tracked wide. Default tracking on a 200px headline looks flabby; default tracking on 18px caps looks like a form field. This single adjustment does more for perceived quality than any other typographic choice.

**The gap is deliberate.** There is nothing between 44px and 100px. If content wants to live there, it belongs in the detail module at 22px instead.

Line spacing on the display setting: 0.85–0.92 of the cap height. Stacked display words should nearly touch.

---

## 8. Output specifications

| Format | Size | Use |
|---|---|---|
| Feed (primary) | 1080 × 1350 | Instagram / Facebook feed. Build here first. |
| Story | 1080 × 1920 | Re-lay the same elements — do not letterbox the feed version. Photo takes the lower 60%, type block centred in the upper 40%. |
| Square | 1080 × 1080 | Only if needed. Crop from feed with the detail module re-anchored. |
| Web | 1600 × 2000 | shccstorm.com.au. Same layout, 1.48× scale. |

Export PNG for graphics with flat fields and large type; JPEG at quality 92 only if file size forces it. Never re-export a JPEG that has already been compressed — rebuild from source.

Filename convention: `shcc-{type}-{surname}-{season}.png` → `shcc-captain-sandhu-2627.png`.

---

## 9. Pre-publish checklist

**Brand**
- [ ] Exactly one teal value used, matching the token
- [ ] Three values only — field, white, teal (plus grey/tint for hierarchy)
- [ ] Two type families maximum; no brush script, no distressed face
- [ ] Logo uncropped, above minimum size, with clear space respected

**Layout**
- [ ] Every element either bleeds fully or sits exactly on the 72px margin — nothing in between
- [ ] Two or three alignment axes at most, all obeyed
- [ ] All secondary information inside one grouped module
- [ ] No mid-sized type (nothing between 44px and 100px)
- [ ] Big type tracked tight, small type tracked wide

**Photo**
- [ ] Tier assessed honestly and template chosen to match
- [ ] House grade applied — desaturated, duotoned, shadows crushed
- [ ] Global grain over the entire canvas, including type and flat fields
- [ ] Eye line on the upper third; top of head cropped
- [ ] No third parties in frame
- [ ] Mask edges checked at 200% around the hairline

**Content**
- [ ] Player name spelled correctly — check against the registration list, not memory
- [ ] Grade identifier correct (`1st XI`, not `1sts`)
- [ ] Figures in club notation (`3/24`, `47*`)
- [ ] Season written consistently (`2026/27`)
- [ ] Player has consented to the photo being published
- [ ] For any player under 18: parental consent obtained, and no personal detail beyond first name, surname and grade

---

## 10. Brief block

Copy, fill, and paste alongside the photo.

```
ANNOUNCEMENT BRIEF — SHCC Storm

Type:              [captain / vice-captain / signing / debut / milestone /
                    player of the match / award / coach / farewell]
Player name:       [Given Surname]
Grade:             [1st XI / 2nd XI / 3rd XI / Under 16s / Women's]
Season:            [2026/27]

Detail field 1:    [e.g. ALL-ROUNDER]
Detail field 2:    [e.g. 6TH SEASON AT THE CLUB]
Detail field 3:    [optional — e.g. 2,140 CAREER RUNS]

Stat or figures:   [optional — e.g. 3/24 and 61*]
Previous club:     [signings only]
Quote:             [optional, max 90 characters]

Photo tier:        [A / B / C / D — or leave blank and assess it]
Output formats:    [feed / story / square / web]
Notes:             [anything else — e.g. "he's in a helmet, face isn't
                    usable", "photo is a crop from the team photo"]
```

---

## 11. Build notes

Consistent with the existing club toolchain — built programmatically in Node, not by hand in a design tool, so a whole season of announcements can be regenerated from data if the brand changes.

- **Recommended stack.** `sharp` for photo processing (greyscale, duotone via `.recomb()` or a tint composite, blur, resize) and `node-canvas` or an SVG-to-PNG pipeline (`resvg`) for layout and typography. `sharp` handles the grade; the layout layer handles type and composition.
- **Tokens in one file.** Colours, type scale, and margins in a single `tokens.json` consumed by every template. When the teal is finally resolved, one edit re-renders everything.
- **Templates as functions.** `renderT1(brief, photoBuffer)` returning a buffer. Each template takes the same brief shape, so switching templates when a photo turns out to be Tier C is a one-line change.
- **Grade as a reusable pipeline.** One `houseGrade(buffer, {halftone: bool})` function applied identically to every photo. Never grade by eye per player.
- **Render and check before delivery.** Export a thumbnail and inspect it — mask edges, type collisions, margin violations — then correct before sending. The same QA loop already used on club decks and letters.
- **Watch the font metrics.** Cap height, not point size, is what the §7 table specifies. Anton's point size and cap height differ substantially; measure once and store the ratio in the tokens file.
