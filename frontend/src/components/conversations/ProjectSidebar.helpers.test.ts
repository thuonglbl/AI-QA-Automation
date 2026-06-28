import { describe, expect, it } from "vitest";
import {
  buildResultTree,
  displayLabel,
  isMarkdown,
  type Artifact,
} from "@/components/conversations/ProjectSidebar";

function mk(name: string, opts: Partial<Artifact> = {}): Artifact {
  return {
    id: opts.id ?? name,
    project_id: "p1",
    kind: opts.kind ?? "requirements",
    name,
    created_at: "2026-06-18T10:00:00Z",
    updated_at: "2026-06-18T10:00:00Z",
    title: opts.title ?? null,
    parent_source_id: opts.parent_source_id ?? null,
    ...opts,
  };
}

describe("displayLabel", () => {
  it("uses the friendly title when present", () => {
    expect(displayLabel(mk("1234/requirement.md", { title: "US01 - Create journey" }))).toBe(
      "US01 - Create journey",
    );
  });

  it("falls back to the name's last segment for raw companions and flat names", () => {
    expect(displayLabel(mk("spec.md"))).toBe("spec.md");
    expect(displayLabel(mk("1234/raw/page.html"))).toBe("page.html");
  });

  it("falls back to the page id (not the basename) for a titleless approved result", () => {
    // Legacy {id}/requirement.md rows predate titles: page id keeps them distinct
    // rather than every row collapsing to the identical "requirement.md".
    expect(displayLabel(mk("99/requirement.md"))).toBe("99");
    expect(displayLabel(mk("99/requirement.md", { title: "   " }))).toBe("99");
  });

  it("labels a test case by its own file, never the shared role folder", () => {
    // Test cases are stored "{role}/{slug}.md"; the first segment is the role folder,
    // shared by every case in that role — using it would label them all identically
    // (the "Attributor" bug). The page-id fallback is scoped to requirements only.
    expect(
      displayLabel(mk("Attributor/verify-attribution-recorded.md", { kind: "testcase" })),
    ).toBe("verify-attribution-recorded.md");
    expect(
      displayLabel(mk("Attributor/verify-no-attribution.md", { kind: "testcase" })),
    ).toBe("verify-no-attribution.md");
    // A persisted title still wins for a test case.
    expect(
      displayLabel(
        mk("Attributor/verify-attribution-recorded.md", {
          kind: "testcase",
          title: "Verify attribution is recorded",
        }),
      ),
    ).toBe("Verify attribution is recorded");
  });
});

describe("isMarkdown", () => {
  it("matches .md (case-insensitive) and rejects other extensions", () => {
    expect(isMarkdown(mk("1234/requirement.md"))).toBe(true);
    expect(isMarkdown(mk("README.MD"))).toBe(true);
    expect(isMarkdown(mk("1234.html"))).toBe(false);
    expect(isMarkdown(mk("1234/requirement.metadata.json"))).toBe(false);
    expect(isMarkdown(mk("img.png"))).toBe(false);
  });
});

describe("buildResultTree", () => {
  it("nests children under their parent by parent_source_id, with depth", () => {
    const root = mk("100/requirement.md", { title: "Root" });
    const childA = mk("101/requirement.md", { title: "A", parent_source_id: "100" });
    const childB = mk("102/requirement.md", { title: "B", parent_source_id: "100" });
    const grandchild = mk("103/requirement.md", { title: "A1", parent_source_id: "101" });

    const rows = buildResultTree([grandchild, childB, root, childA]);
    const flat = rows.map((r) => [displayLabel(r.artifact), r.depth] as const);

    // Pre-order, alphabetical by label within siblings.
    expect(flat).toEqual([
      ["Root", 0],
      ["A", 1],
      ["A1", 2],
      ["B", 1],
    ]);
  });

  it("treats a result whose parent is not in the set as a root", () => {
    const orphan = mk("200/requirement.md", { title: "Orphan", parent_source_id: "999" });
    const rows = buildResultTree([orphan]);
    expect(rows).toEqual([{ artifact: orphan, depth: 0 }]);
  });

  it("is flat when no parent links exist", () => {
    const a = mk("1/requirement.md", { title: "A" });
    const b = mk("2/requirement.md", { title: "B" });
    const rows = buildResultTree([b, a]);
    expect(rows.map((r) => r.depth)).toEqual([0, 0]);
  });

  it("de-duplicates a leftover {id}.md draft against its approved {id}/requirement.md", () => {
    const draft = mk("100.md", { id: "draft", title: null });
    const approved = mk("100/requirement.md", { id: "approved", title: "Personal Travel Plan" });
    const rows = buildResultTree([draft, approved]);
    expect(rows).toHaveLength(1);
    expect(rows[0]!.artifact.id).toBe("approved");
    expect(displayLabel(rows[0]!.artifact)).toBe("Personal Travel Plan");
  });

  it("nests children referencing the parent's page id even when the parent is {id}/requirement.md", () => {
    const root = mk("100/requirement.md", { title: "Root" });
    const child = mk("101/requirement.md", { title: "Child", parent_source_id: "100" });
    const rows = buildResultTree([child, root]);
    expect(rows.map((r) => [displayLabel(r.artifact), r.depth])).toEqual([
      ["Root", 0],
      ["Child", 1],
    ]);
  });

  it("does not loop on a parent/child cycle", () => {
    const a = mk("1/requirement.md", { title: "A", parent_source_id: "2" });
    const b = mk("2/requirement.md", { title: "B", parent_source_id: "1" });
    const rows = buildResultTree([a, b]);
    // Both appear exactly once; no infinite recursion.
    expect(rows).toHaveLength(2);
    expect(new Set(rows.map((r) => r.artifact.id))).toEqual(new Set(["1/requirement.md", "2/requirement.md"]));
  });
  it("synthesizes missing intermediate ancestors if provided in allEntries", () => {
    // A grand-child requirement .md file.
    // The immediate parent is "101", which has no .md file in the results.
    // The root is "100", which has a .md file.
    const root = mk("100/requirement.md", { title: "Root" });
    const grandchild = mk("102/requirement.md", { title: "Grandchild", parent_source_id: "101", ancestor_source_ids: ["100", "101"] });

    // The intermediate parent ONLY exists as a non-markdown artifact (e.g., raw HTML)
    const intermediateFolderRaw = mk("101/raw_content.html", { title: "Intermediate Folder", parent_source_id: "100", ancestor_source_ids: ["100"] });

    // If we only pass results, grandchild attaches to root
    const flatRows = buildResultTree([grandchild, root]);
    expect(flatRows.map((r) => [displayLabel(r.artifact), r.depth])).toEqual([
      ["Root", 0],
      ["Grandchild", 1],
    ]);

    // If we pass allEntries, the intermediate folder is synthesized
    const hierRows = buildResultTree([grandchild, root], [root, grandchild, intermediateFolderRaw]);
    expect(hierRows.map((r) => [displayLabel(r.artifact), r.depth])).toEqual([
      ["Root", 0],
      ["Intermediate Folder", 1],
      ["Grandchild", 2],
    ]);
  });
});
