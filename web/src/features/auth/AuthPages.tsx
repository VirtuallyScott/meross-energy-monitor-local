import { useMutation, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useState } from "react";

import { Alert, Button, Field } from "../../components/ui";
import { errorMessage, post } from "../../lib/api";
import "./auth.css";

function AuthFrame({
  title,
  lead,
  children,
}: {
  title: string;
  lead: string;
  children: React.ReactNode;
}) {
  return (
    <main className="auth">
      <div className="auth-card">
        <p className="eyebrow">Energy Hub · local</p>
        <h1>{title}</h1>
        <p className="auth-lead">{lead}</p>
        {children}
      </div>
    </main>
  );
}

export function LoginPage() {
  const qc = useQueryClient();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const login = useMutation({
    mutationFn: () => post("/auth/login", { username, password }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["me"] }),
  });
  const submit = (e: FormEvent) => {
    e.preventDefault();
    login.mutate();
  };
  return (
    <AuthFrame title="Sign in" lead="Monitor and manage the energy monitors on this network.">
      <form onSubmit={submit}>
        {login.isError && <Alert>{errorMessage(login.error)}</Alert>}
        <Field
          label="Username"
          autoComplete="username"
          required
          value={username}
          onChange={(e) => setUsername(e.target.value)}
        />
        <Field
          label="Password"
          type="password"
          autoComplete="current-password"
          required
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
        <Button tone="primary" type="submit" disabled={login.isPending}>
          {login.isPending ? "Signing in…" : "Sign in"}
        </Button>
      </form>
    </AuthFrame>
  );
}

const DEFAULT_TZ = Intl.DateTimeFormat().resolvedOptions().timeZone;

export function SetupPage() {
  const qc = useQueryClient();
  const [form, setForm] = useState({
    setup_token: "",
    username: "",
    password: "",
    site_name: "Home",
    time_zone: DEFAULT_TZ,
  });
  const set = (key: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setForm({ ...form, [key]: e.target.value });
  const setup = useMutation({
    mutationFn: async () => {
      await post("/setup", form);
      await post("/auth/login", { username: form.username, password: form.password });
    },
    onSuccess: () => qc.invalidateQueries(),
  });
  return (
    <AuthFrame
      title="First-run setup"
      lead="Create the administrator account and your first site. The setup token is in the API container log or the setup_token secret."
    >
      <form
        onSubmit={(e) => {
          e.preventDefault();
          setup.mutate();
        }}
      >
        {setup.isError && <Alert>{errorMessage(setup.error)}</Alert>}
        <Field
          label="Setup token"
          required
          value={form.setup_token}
          onChange={set("setup_token")}
          autoComplete="off"
        />
        <Field
          label="Admin username"
          required
          value={form.username}
          onChange={set("username")}
          autoComplete="username"
          pattern="[A-Za-z0-9._\-]{3,64}"
        />
        <Field
          label="Password"
          type="password"
          required
          minLength={12}
          value={form.password}
          onChange={set("password")}
          autoComplete="new-password"
          hint="At least 12 characters."
        />
        <Field label="Site name" required value={form.site_name} onChange={set("site_name")} />
        <Field
          label="Time zone"
          required
          value={form.time_zone}
          onChange={set("time_zone")}
          hint="IANA name, for example America/New_York. Used for days and billing cycles."
        />
        <Button tone="primary" type="submit" disabled={setup.isPending}>
          {setup.isPending ? "Setting up…" : "Create admin and site"}
        </Button>
      </form>
    </AuthFrame>
  );
}
