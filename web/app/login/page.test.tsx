import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

const { signInMock, searchParamsMock } = vi.hoisted(() => ({
  signInMock: vi.fn(),
  searchParamsMock: new URLSearchParams(),
}));

vi.mock("next-auth/react", () => ({
  signIn: signInMock,
}));

vi.mock("next/navigation", () => ({
  useSearchParams: () => searchParamsMock,
}));

import { LoginForm } from "@/app/login/login-form";

const originalLocation = window.location;

afterEach(() => {
  signInMock.mockReset();
  searchParamsMock.forEach((_, key) => searchParamsMock.delete(key));
  Object.defineProperty(window, "location", {
    configurable: true,
    value: originalLocation,
  });
});

test("login page renders Continue with Google", () => {
  render(<LoginForm googleConfigured />);

  expect(screen.getByRole("button", { name: /continue with google/i })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /^sign in$/i })).toBeInTheDocument();
});

test("Continue with Google preserves callbackUrl", async () => {
  const user = userEvent.setup();
  searchParamsMock.set("callbackUrl", "/chat/thread-1");

  render(<LoginForm googleConfigured />);

  await user.click(screen.getByRole("button", { name: /continue with google/i }));

  expect(signInMock).toHaveBeenCalledWith("google", { callbackUrl: "/chat/thread-1" });
});

test("password form still signs in with credentials", async () => {
  const user = userEvent.setup();
  signInMock.mockResolvedValue({ url: "/chat/thread-1" });
  const assign = vi.fn();
  Object.defineProperty(window, "location", {
    configurable: true,
    value: { assign },
  });

  render(<LoginForm googleConfigured />);

  await user.type(screen.getByLabelText(/username/i), "admin");
  await user.type(screen.getByLabelText(/password/i), "secret");
  await user.click(screen.getByRole("button", { name: /^sign in$/i }));

  await waitFor(() =>
    expect(signInMock).toHaveBeenCalledWith("credentials", {
      username: "admin",
      password: "secret",
      callbackUrl: "/",
      redirect: false,
    }),
  );
  expect(assign).toHaveBeenCalledWith("/chat/thread-1");
});

test("Google button shows a clear message when server config is missing", async () => {
  const user = userEvent.setup();

  render(<LoginForm googleConfigured={false} />);

  await user.click(screen.getByRole("button", { name: /continue with google/i }));

  expect(signInMock).not.toHaveBeenCalled();
  expect(screen.getByRole("alert")).toHaveTextContent(
    "Google sign-in is not configured on this server.",
  );
});
