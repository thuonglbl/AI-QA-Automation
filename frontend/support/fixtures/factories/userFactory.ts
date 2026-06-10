import { faker } from "@faker-js/faker";

export type TestUser = {
  id: string;
  email: string;
  displayName: string;
  role: "admin" | "standard";
  password: string;
};

export class UserFactory {
  private readonly createdUsers: TestUser[] = [];

  create(overrides: Partial<TestUser> = {}): TestUser {
    const user: TestUser = {
      id: faker.string.uuid(),
      email: faker.internet.email({ provider: "example.test" }).toLowerCase(),
      displayName: faker.person.fullName(),
      role: "standard",
      password: faker.internet.password({ length: 16 }),
      ...overrides,
    };

    this.createdUsers.push(user);
    return user;
  }

  all(): TestUser[] {
    return [...this.createdUsers];
  }

  async cleanup(): Promise<void> {
    this.createdUsers.splice(0, this.createdUsers.length);
  }
}
