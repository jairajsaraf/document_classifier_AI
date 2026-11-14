# UI library evaluation (Phase 4, step 1)

Written 2026-11-13. Evaluation only: no UI code, nothing installed. Status: approved 2026-11-13 by the project owner: shadcn as the library, and the design direction in section 6. Phase 4b may start.

Claim labels: **confirmed** (source named), **inferred**, **unknown**. Every `npm view` below was run 2026-11-13 from this machine (Node v24.18.1).

## Recommendation

**shadcn/ui, confirming the plan's call, with `@tanstack/react-table` for the table and `react-pdf` for the PDF pane.**

Reasons, in order of weight:

1. **Neither library ships either of the two hard pieces, so the library choice buys little there.** Neither has a ready table or a PDF evidence pane (section 2). shadcn at least documents the table path (a guide built on TanStack Table). `@ui-sdk/react` has no table at all.
2. **`@ui-sdk/react` is a day-old beta with a hard React 19 floor.** Published 2026-11-12, `latest` is `0.1.0-beta.1`, and its docs say "UI SDK is in beta, and some APIs may still change". shadcn's CLI has been published since 2024-07 and is at 4.23.0.
3. **Its main differentiator does nothing for this audience.** createAgent/WebMCP only works in a browser that exposes `document.modelContext`; elsewhere `registerTools` "does nothing". A reviewer with 5 minutes gets no value from it (section 5).
4. **Styling cost is lower and more familiar with shadcn + Tailwind**, and Tailwind is already declared in `frontend/package.json`.

The best case against my pick, stated once: `@ui-sdk` ships keyboard/focus/ARIA behaviour for 55 components with no styles of its own, which is real accessibility value for the Phase 4 accessibility check. I do not think it outweighs the beta risk for a portfolio piece that must work first time. shadcn's components are described as accessible (confirmed: https://ui.shadcn.com/docs), but I did not test that.

**Decision needed from you, applies to both options:** the stack in `frontend/package.json` (Next 14, React 18, `react-pdf` ^7.6) is out of date against what `@ui-sdk` or the current `react-pdf` needs. See "Version baseline" at the end.

## 1. Fresh `npm view` (run 2026-11-13)

| Command | Result (confirmed: command output) |
|---|---|
| `npm view @ui-sdk/react name version dist-tags license time.created time.modified repository.url peerDependencies` | version `0.1.0-beta.1`; dist-tags `latest: 0.1.0-beta.1`, `beta: 0.1.0-beta.2`; Apache-2.0; created 2026-11-12T17:06Z; modified 2026-11-13T13:04Z; repo `vercel-labs/ui`; peers `react >=19`, `react-dom >=19`, `@types/react >=19.2.10`, `@ui-sdk/core ^0.1.0-beta.1` |
| `npm view @ui-sdk/react time --json` | `0.0.0-stage` 2026-11-12T17:06Z; `0.1.0-beta.1` 2026-11-12T17:09Z; `0.1.0-beta.2` 2026-11-13T13:04Z. Matches the plan's record. |
| `npm view @ui-sdk/react versions --json` | three versions ever: `0.0.0-stage`, `0.1.0-beta.1`, `0.1.0-beta.2` |
| `npm view @ui-sdk/react@0.1.0-beta.2 peerDependencies --json` | same React floor (`>=19`); core `^0.1.0-beta.2` |
| `npm view @ui-sdk/core version dist-tags --json` | `latest` 0.1.0-beta.1, `beta` 0.1.0-beta.2 |
| `npm view shadcn name version dist-tags license time.created time.modified repository.url` | `4.23.0` (= `latest`); also `canary`, `rc`, `beta` tags; MIT; created 2024-07-09; last modified 2026-10-27; repo `shadcn-ui/ui` |
| `npm view shadcn engines bin --json` | node `>=20.18.1`; bin `shadcn` |
| `npm view react-pdf name version dist-tags license time.modified peerDependencies` | `11.0.0`; MIT; modified 2026-09-10; peers `react ^19.0.0`, `react-dom ^19.0.0` |
| `npm view @tanstack/react-table ...` | `9.3.1`; MIT; peer `react >=18` |
| `npm view next version engines peerDependencies --json` | `16.4.6`; node `>=20.9.0`; peers `react ^18.2.0 \|\| ^19.0.0` (plus a 19 RC) |
| `npm view tailwindcss version` | `4.3.5` |

**What "shadcn" is, version-wise.** The npm package `shadcn` is the CLI (confirmed: `bin: shadcn`). The docs call it "a code distribution platform": you receive "the actual component code" instead of importing from npm (confirmed: https://ui.shadcn.com/docs). Consequences:

- Components land in `components/ui/` in this repo (confirmed: https://ui.shadcn.com/docs/installation/next). No component version appears in `package.json`; the repo owns the code.
- Upside: no upstream release can break the UI, and the code can be edited freely. Downside (inferred): upstream security or accessibility fixes do not arrive by themselves.
- How upstream updates are pulled: **unknown**. The docs page I read poses the question and does not answer it.
- Which runtime packages the components pull in (Radix or similar): **unknown**, not read. The install step would list them.

## 2. Coverage: sortable/filterable table and PDF evidence pane

| Need | `@ui-sdk/react` | shadcn | Verdict |
|---|---|---|---|
| Sortable, filterable table | **None.** The 55-component list (https://ui-sdk.dev/docs/react/components) has no Table or Data Grid. Closest: Listbox, Tree, Pagination, Select, Combobox, Segmented Control (useful as filter controls). Sorting is not mentioned. (confirmed: that page) | **A guide, not a component.** `Table` is styled markup with no built-in sorting (confirmed: https://ui.shadcn.com/docs/components/radix/table). The Data Table page is "a guide on how to build your own" on TanStack Table v9, with a sortable email header and a text filter (confirmed: https://ui.shadcn.com/docs/components/radix/data-table). | Build on `@tanstack/react-table` in both cases. It is headless; that it works with ui-sdk is inferred, not tested. shadcn gives a styled shell and a worked example; ui-sdk gives neither. |
| PDF pane: jump to cited page, show cited quote | **None.** No PDF or document viewer in the component list (confirmed: same page). | **None** in the pages I read (inferred: I did not search the whole registry). | The plan's expectation holds: **neither ships it; build on `react-pdf`.** |

**`react-pdf` covers the mechanics** (confirmed: https://github.com/wojtekmaj/react-pdf/blob/main/packages/react-pdf/README.md):

- Jump to a page: pass `pageNumber` (1-based) to `<Page>`. "Click citation, show page N" is one state variable.
- Text layer: `renderTextLayer` is on by default; import `react-pdf/dist/Page/TextLayer.css`.
- Quote highlighting: no search API is documented. The README's approach is `customTextRenderer({ str, itemIndex })` returning an HTML string with matches wrapped in `<mark>`, and the output must be sanitised.
- **Inferred risk, not tested:** `customTextRenderer` works per text item, so a quote that spans several PDF text items will not match a single-string regex. Phase 4b should not promise exact highlighting. Safe design: always show the quote text in the side panel (the API supplies it, with the `verified` flag) and highlight on the page as best effort.
- Next.js: skip SSR for the module that uses it, and set `pdfjs.GlobalWorkerOptions.workerSrc` in the same module that renders `<Document>`/`<Page>` (confirmed: same README).
- Requirements of the current major: React 19, Node 22.13+, Chrome 125+ / Safari 18+; Chrome 125 needs a `URL.parse()` polyfill (confirmed: same README).
- Not checked: the PDF.js worker's size and load time on the Render free instance.

## 3. Static export check

Page: https://nextjs.org/docs/app/guides/static-exports (header says last updated 2026-08-09).

- Enable with `output: 'export'` in `next.config.js`; `next build` writes `out/` (confirmed). FastAPI can serve that folder (inferred).
- Client Components are supported and prerendered at build; browser-only APIs must be used inside `useEffect` (confirmed).
- **Unsupported (confirmed, same page):** dynamic routes without `generateStaticParams()` or with `dynamicParams: true`, rewrites, redirects, headers, cookies, Server Actions, default-loader Image Optimization, Proxy, ISR, Draft Mode.
- **Consequence for 4b (inferred from the above):** the document view cannot be `/documents/[id]`, because ids are created at runtime by uploads. Use `/document?id=...` read client-side, call `/api/...` on the same origin (no rewrites exist in an export, and none are needed in one container), and use plain `<img>` instead of `next/image`.
- **`@ui-sdk/react`:** its docs do not mention static export or prerender. Its server-rendering page says components ship `"use client"`, send initial HTML with ARIA state, and hydrate in the browser (https://ui-sdk.dev/docs/react/server-rendering). I infer it works in an export; **untested**.
- **shadcn:** the pages I read do not mention static export. Its components are plain React client components living in your repo (inferred), so I expect it to work; **untested**.
- `react-pdf`: needs the no-SSR import described above (inferred to be compatible with an export).

## 4. Styling cost for two screens

**shadcn**
- One-time: `shadcn init` (Tailwind and CSS-variable theme) and an `@/*` alias in `tsconfig.json` (confirmed: https://ui.shadcn.com/docs/installation/next). That page does not state the Tailwind version. The Tailwind v4 page says new projects start on Tailwind v4 + React 19, existing v3/React 18 apps keep working (https://ui.shadcn.com/docs/tailwind-v4).
- Per component: `shadcn add <name>`, one file each in this repo. I estimate 8 to 12 for these screens (inferred): table, badge, button, input, select, dialog, toast, tabs or similar.
- Consistency comes from the shared CSS-variable tokens set at init (inferred from the install flow). Least effort of the two for a polished result.
- Maintenance: you own the copied files.

**`@ui-sdk/react`**
- Components render no styles by default; `@ui-sdk/core/web.css` gives an optional default look. Source for `web.css`: the official `ui-sdk` skill in this session. The web docs page I read on styling did not cover it.
- Style by `data-slot` and state attributes (`data-open`, `data-pressed`) with plain CSS or Tailwind variants (confirmed: https://ui-sdk.dev/docs/core/kernel/style-a-component). Declare the small `@layer ui-sdk;` cascade layer (confirmed: that page points to it; the skill states the rule).
- The table, badge and PDF pane are not covered, so they need hand styling to match, plus a manual contrast check in a real browser (per the skill).
- Estimate: higher than shadcn (inferred). The larger cost is beta churn: an API change breaks the build.

## 5. Agent-readiness verdict (for a 5-minute reviewer)

**`@ui-sdk/react`: ready in principle, no value for this audience.**
- `createAgent` connects an agent to the ui-sdk components on the page: it reads their state, sees their actions and calls them. You can pass the `agentTools` (`snapshot`, `act`, `query`) to your own model SDK, or register them through WebMCP (confirmed: https://ui-sdk.dev/docs/agents/connect-an-agent).
- WebMCP needs a browser that provides `document.modelContext.registerTool`; otherwise `registerTools` "does nothing" (confirmed: https://ui-sdk.dev/docs/agents/connect-an-agent/webmcp). That page names no supported browsers or flags (unknown which browsers have it).
- Only ui-sdk components are visible to the bridge (inferred from the page's wording). The table and PDF pane, which a reviewer actually looks at, would be built outside it.
- Wiring your own model SDK to it would add a second model path and a cost/abuse surface on an open-upload free demo (inferred). The plan does not ask for it and counts agent features as worth nothing for this audience.

**shadcn: no runtime agent features, none needed.** Its MCP server is a dev-time tool that lets assistants browse and install registry components; it does not affect the shipped app (confirmed: https://ui.shadcn.com/docs/mcp).

The official `ui-sdk` skill was read as one source. It is a vendor document; I labelled each claim I took from it and it did not change the recommendation.

## 6. Avoiding a generic-looking UI (the `unslop` skill)

You asked for the `unslop` skill's rules to apply. Source: the `unslop` skill in this session (by Damir Sokolovsky, CC BY 4.0). Its process says to write a five-line direction and wait for your answer before editing, so I am **not** setting the design direction here; that belongs at the start of 4b. What this document can say:

- **A library choice does not decide the look; its defaults do.** shadcn's stock theme is a widely copied default (inferred, my judgement, not sourced). Using it unchanged is the main generic-look risk of my recommendation. Mitigation, all inside shadcn's own model (CSS-variable tokens set at `init`, files you own): replace the default neutral ramp and accent with a deliberate one, one type family plus at most one partner, 4px spacing grid, one icon set at one size, hairline borders, no gradients or glows. These are the skill's rules.
- **`@ui-sdk` is not safer here.** It renders no styles, so every pixel is a design decision I would make from scratch, with `web.css` as the only default (see section 4). That is more control but more room to land on a template by accident.
- **Where the richness should go (the skill's "moments").** For this product the natural moment is the evidence itself: the PDF page with the cited quote shown beside the label and reasons, and a `verified` mark on each citation. Chrome stays quiet. No decorative images; the skill says dashboards and app screens rarely need them.
- **Copy rules that fit these two screens:** sentence-case labels, no exclamation marks or greeting headlines, no hype words, real-looking seeded data (TC1-TC5), and the eval numbers in the header strip stated with what they compare to. The "do not upload real personal data" notice stays plain text.
- **Proposed direction (for your approval; nothing is built from it until you say so).** The skill requires these five lines and a pause for your answer. Derived from what the product does, not from trend:
  - **Product:** shows a reviewer what an AI labelled a document, why, and where in the PDF the evidence is, so they can approve or override.
  - **Character:** calm, exact, a little severe. Not friendly or playful, because the labels are about sensitive data.
  - **World:** a records-office review desk: paper, margin notes, a reviewer's pencil. Sets the tint of the neutrals (a barely warm grey ramp) and the accent (one muted redline red, kept for "Highly Sensitive", unsafe and the selected citation).
  - **Moment:** one, the PDF page with the cited quote marked, beside label, reasons and citations. Everything else is quiet.
  - **Signature:** the citation chip, a small mono `p.3` with a `verified` tick, used wherever a page is referenced and nowhere else.
  - Type: one sans for the interface and a mono for figures and page references. Sentence case, weights 400 and 500.
  - If you want a different direction, say so now; the choice of library does not depend on it.

## Version baseline (applies to both options)

Confirmed from `frontend/package.json`: Next `^14.0.4`, React `^18.2.0`, `react-pdf ^7.6.0`, Tailwind `^3.3.6`, `react-query ^3.39.3`. Only `frontend/public/index.html` is tracked.

- `@ui-sdk/react` needs React `>=19` (confirmed: `npm view`). Which Next versions first accept React 19: **unknown** from the docs I read. `npm view next` shows 16.4.6 accepting `^18.2.0 || ^19.0.0`.
- `react-pdf` latest (11.0.0) needs React 19. Keeping React 18 would mean an older `react-pdf` major; whether `react-pdf` 7.x works well in an export build today is **unknown**.
- shadcn works on React 18 + Tailwind 3 or React 19 + Tailwind 4 (confirmed: tailwind-v4 page).
- Suggestion for 4b, for your decision and not done: start on current Next with React 19, and drop the declared dependencies the two screens do not use (`socket.io-client`, `react-image-annotate`, `recharts`, `axios`, `react-query`, `zustand` and others). That deletes lines from a file, so I would ask first.

## Adjacent issues noticed (not acted on)

- `frontend/package.json` has a `jest` test script and many unused dependencies with no source tree behind them.
- `react-pdf`'s Node 22.13+ requirement means the Dockerfile's frontend build stage needs a matching Node image (Dockerfile not read in this task).
- Phase 4b should measure PDF.js worker load on Render free before judging Lighthouse numbers.

## Not done

No install, scaffold, build or browser test was run, so every "works in a static export" statement is inferred. The first real test is the Phase 4b build.
