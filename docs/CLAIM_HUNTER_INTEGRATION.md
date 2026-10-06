# Claim Hunter AI integration plan

This branch is the safe integration workspace for combining the existing settlement-claims-agent with the useful parts of the separate Lovable Claim Hunter AI project.

## Source snapshots reviewed

- Lovable project: Claim Hunter AI
- Lovable commit: `689edd1eaea4c43ecb188b6f7b9efd3f6025d11a`
- Existing application: `nugglebug87/settlement-claims-agent`
- Existing Claims Search / Form Filler work: merged PR #2

## Preserve from settlement-claims-agent

- Existing Python application and Railway deployment configuration.
- Claims Search and Form Filler workflow from PR #2.
- Manual/human submission and confirmation capture.
- Approval invalidation when mapped claim data changes.
- Post-handoff edit protections.
- Existing tests and working behavior.

## Port from Lovable Claim Hunter AI

- Claim Hunter AI product/visual direction.
- Eligibility profile questionnaire and weighted completeness score.
- AI eligibility screening behavior: never invent missing facts; expose unknowns.
- Claim statuses and priority/deadline scoring.
- Research concepts: web settlement discovery, CourtListener/RECAP lookup, URL normalization and deduplication.
- Approval queue concepts for factual/legal attestations.
- Dashboard/workspace concepts and CSV/report export.

## Important Lovable limitations discovered

- The Supabase database is enabled, but `drizzle/schema.ts` is currently blank.
- The live Lovable source currently exposes only landing and auth routes.
- Auth currently redirects signed-in users back to `/`; there is no live authenticated dashboard route.
- Research/server logic references tables such as `claims`, `eligibility_profiles`, `approvals`, `audit_log`, and `research_sources`, but the current schema does not define them.
- External website autofill, electronic signatures, and automated submission are intentionally out of scope for this integration phase.

## Integration order

1. Keep the existing app runnable and tests green.
2. Add Claim Hunter eligibility/profile and priority-scoring domain logic.
3. Add research-source normalization/deduplication and CourtListener integration behind existing server architecture.
4. Connect those capabilities to the existing Claims Search workflow.
5. Integrate the existing Form Filler into a single claim workspace.
6. Add dashboard/profile/research/approval views without breaking the existing filing path.
7. Test one complete workflow: discover -> screen -> prepare -> approve -> manual submit -> confirmation/tracking.
8. Only after verification, decide whether this branch should replace production.

## Explicitly not included yet

- Automatic electronic signatures.
- Automatic final submission to settlement administrators.
- CAPTCHA bypassing.
- Production deployment.

No production deployment should occur merely by merging this planning document.
