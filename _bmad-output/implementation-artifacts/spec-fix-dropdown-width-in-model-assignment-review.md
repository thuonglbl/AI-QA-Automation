---
title: 'fix-dropdown-width-in-model-assignment-review'
type: 'bugfix'
created: '2026-05-30'
status: 'done'
route: 'one-shot'
---

# fix-dropdown-width-in-model-assignment-review

## Intent

**Problem:** The popup "Connected successfully to On-Premises!" had a fixed `max-w-[600px]` width, causing the dropdown to truncate long model names instead of displaying them fully.

**Approach:** Changed the fixed `max-w-[600px]` constraint on the popup container to `max-w-[90vw] md:max-w-max` to allow flexible expansion based on the selected model name's width, ensuring it displays completely without truncation.

## Suggested Review Order

1. [frontend/src/components/ModelAssignmentReview.tsx](file:///frontend/src/components/ModelAssignmentReview.tsx)
   - Updated `div` wrapper from `max-w-[600px]` to `max-w-[90vw] md:max-w-max`
