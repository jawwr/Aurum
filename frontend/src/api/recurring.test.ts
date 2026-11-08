import { afterEach, describe, expect, it, vi } from "vitest";
import { postRecurring } from "@/api/recurring";

// api/client.ts pulls in the credential store (IndexedDB/WebCrypto) at module
// load; the request layer under test doesn't need any of that.
vi.mock("@/lib/auth", () => ({
  getAuthHeader: () => null,
  clearCredentials: () => undefined,
}));

function mockFetchResponse(status: number, body: unknown) {
  return vi.fn().mockResolvedValue({
    ok: status >= 200 && status < 300,
    status,
    statusText: "",
    json: async () => body,
    text: async () => JSON.stringify(body),
  } as unknown as Response);
}

describe("postRecurring", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("posts an empty link when creating a new transaction from the template", async () => {
    const fetchMock = mockFetchResponse(201, { id: 7 });
    vi.stubGlobal("fetch", fetchMock);

    await postRecurring(7, null);

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/api/recurring/7/post");
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body as string)).toEqual({ transaction_id: null });
  });

  it("sends the chosen existing transaction id so it gets linked instead", async () => {
    const fetchMock = mockFetchResponse(201, { id: 7 });
    vi.stubGlobal("fetch", fetchMock);

    await postRecurring(7, 42);

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/api/recurring/7/post");
    expect(JSON.parse(init.body as string)).toEqual({ transaction_id: 42 });
  });

  it("surfaces the server's rejection (e.g. already paid, 409) as a thrown error", async () => {
    vi.stubGlobal(
      "fetch",
      mockFetchResponse(409, { detail: "Recurring transaction is already posted for the current period" })
    );

    await expect(postRecurring(7, null)).rejects.toMatchObject({ status: 409 });
  });
});
