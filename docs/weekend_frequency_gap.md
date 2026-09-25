# Why on-time performance doesn't show the weekend gap

A fair challenge to the numbers in `docs/week2_findings.md`: weekday on-time performance (67.8%) and weekend (70.5%) are only 2.7 points apart. If weekend service is really that much worse, why doesn't the headline number show it?

Because on-time performance and service existence measure genuinely different things, and OTP is blind to the one that actually differs most. OTP asks *"did the trips that were scheduled arrive close to their scheduled time"* — a route running once every 30 minutes, dead on schedule every time, scores 100%. It says nothing about whether that route, or dozens of others, exist on the timetable at all that day.

## Finding 1: a real fraction of routes don't run on weekends at all

![The weekday/weekend gap on-time performance alone doesn't show](images/weekend_frequency_gap.png)

- **20,853 scheduled trips** on a weekday (Thursday, 17 September 2026), across **494 distinct routes**
- **Saturday: 13,002 trips** (38% fewer), across only **364 routes**
- **Sunday: 11,149 trips** (47% fewer), across only **332 routes**

**149 routes that run on a weekday have zero Saturday service**, carrying **3,439,045 weekday riders** (7.4% of all weekday ridership). **181 routes have zero Sunday service**, carrying **4,429,688 weekday riders** (9.5%). This is the actual weekend gap — not a route running less often, a route not existing on the weekend timetable at all — and it's invisible to on-time performance by construction: a route that doesn't run can't be measured as late or early.

## Finding 2: among the routes that do keep running, headway is roughly similar

For each route, average wait for a random arrival ≈ half its average headway, derived from that route's own actual scheduled span (first to last departure ÷ trip count), weighted by real ridership so busy routes count more than quiet ones. This deliberately **excludes** the routes in Finding 1 (no span exists for a route with zero trips), so it answers a narrower question: *for a rider whose route still runs on weekends, how much longer do they wait?*

- Weekday: **7.8 minutes** average expected wait (442 routes)
- Weekend: **7.7 minutes** average expected wait (329 routes)

Surprisingly close — the routes that survive onto the weekend timetable (largely the busiest ones, since low-ridership routes are exactly the ones likeliest to be cut entirely) tend to keep something close to their weekday frequency. **The weekend problem is concentrated in which routes exist, not primarily in how often the survivors run** — the opposite emphasis from the Manly/Lota case study, where the *specific* corridor examined does keep running on weekends but at a much-reduced flat 30-minute rail headway. Both are real; they're just different failure modes on different parts of the network.

## Reconciling this with the OTP numbers

All three findings are true at once: weekday and weekend on-time performance are close (67.8% vs 70.5%) because OTP only measures the trips that exist; a real chunk of the network (~10% of weekday ridership on Sundays) has zero weekend service at all; and among routes that do survive, frequency holds up better than expected. **Reliability, frequency, and existence are three different axes** — this project's early framing (`docs/manly_lota_service_gap.md`) already separated reliability from frequency for one corridor; this confirms coverage is a third, distinct axis at the network level.

## Method & caveats

- **Route existence** is checked by route short name having ≥1 scheduled trip that day — a route with even a single weekend trip counts as "exists", so this likely *understates* how thin some "surviving" weekend services really are.
- **Weekday ridership is used to weight both the vanished-route and headway findings** (the OD data's own "weekend" bucket obviously can't tell us about riders on routes that don't run that day) — it's the best available proxy for how many people would be affected if they tried to travel that route on a weekend.
- Headway needs ≥3 scheduled trips that day to estimate at all, and is derived from each route's own first-to-last departure span, not an assumed operating-hours constant — a route that only runs peak hours isn't penalised for "missing" overnight service it was never scheduled to provide. It also means a route whose operating *span* shrinks on weekends (starts later, finishes earlier) while keeping similar trip density within that shorter window won't show much headway change here — that's a real limitation of this specific metric, not a claim that span-shrinkage doesn't matter.
- Weekend headway averages Saturday and Sunday computed **separately** (not by merging both days' trips into one span, which would double-count and understate headway by roughly 2x — a bug caught and fixed while building this analysis).
