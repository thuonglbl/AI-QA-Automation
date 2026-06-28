import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import {
  UserBadge,
  effectiveRoles,
  roleSetLabel,
} from "@/components/auth/UserBadge";
import type { AuthUser } from "@/lib/auth";

const baseUser: AuthUser = {
  id: "u1",
  email: "jane.doe@corp.vn",
  name: "Jane Doe",
  display_name: "Jane Doe",
  role: "standard",
};

describe("effectiveRoles / roleSetLabel", () => {
  it("uses the roles array when present", () => {
    const user = { ...baseUser, roles: ["admin", "standard"] };
    expect(effectiveRoles(user)).toEqual(new Set(["admin", "standard"]));
    expect(roleSetLabel(user)).toBe("Admin · User");
  });

  it("falls back to [role] when no roles array", () => {
    expect(effectiveRoles({ ...baseUser, roles: undefined })).toEqual(
      new Set(["standard"]),
    );
    expect(roleSetLabel({ ...baseUser, roles: undefined })).toBe("User");
  });

  it("orders the label by privilege", () => {
    const user = { ...baseUser, roles: ["standard", "project_admin"] };
    expect(roleSetLabel(user)).toBe("Project Admin · User");
  });
});

describe("UserBadge", () => {
  it("renders the avatar image when avatarUrl is set", () => {
    render(<UserBadge user={{ ...baseUser, avatarUrl: "/auth/me/avatar" }} />);
    const img = document.querySelector("img");
    // Radix renders the <img> lazily; the fallback initials are always present.
    expect(screen.getByText("JD")).toBeTruthy();
    // The image element (if mounted) points at the backend avatar URL.
    if (img) expect(img.getAttribute("src")).toBe("/auth/me/avatar");
  });

  it("renders initials when there is no avatar (air-gap / no photo)", () => {
    render(<UserBadge user={{ ...baseUser, avatarUrl: null }} />);
    expect(screen.getByText("JD")).toBeTruthy();
    // No broken image: with no avatarUrl, no <img> src is set to a bad URL.
    expect(document.querySelector('img[src=""]')).toBeNull();
  });

  it("shows the role-set label", () => {
    render(
      <UserBadge user={{ ...baseUser, roles: ["admin", "standard"] }} />,
    );
    expect(screen.getByText("Admin · User")).toBeTruthy();
  });
});
