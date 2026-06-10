import type { APIRequestContext } from "@playwright/test";

export type ApiClientOptions = {
  baseURL?: string;
  request: APIRequestContext;
};

export class ApiClient {
  private readonly baseURL: string;
  private readonly request: APIRequestContext;

  constructor({
    baseURL = process.env.API_URL ?? "http://localhost:8000",
    request,
  }: ApiClientOptions) {
    this.baseURL = baseURL.replace(/\/$/, "");
    this.request = request;
  }

  async getHealth(): Promise<unknown> {
    const response = await this.request.get(`${this.baseURL}/health`);

    if (!response.ok()) {
      throw new Error(
        `Health check failed with ${response.status()} ${response.statusText()}`,
      );
    }

    return response.json();
  }
}
