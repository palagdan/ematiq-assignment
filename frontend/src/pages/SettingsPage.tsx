import { useMutation, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2Icon, KeyRoundIcon, UserIcon } from "lucide-react";
import { type FormEvent, useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { api } from "@/api/client";
import { keys, useAccount, useProviders } from "@/api/hooks";
import type { Account, User } from "@/api/types";
import { GoogleIcon } from "@/components/GoogleIcon";
import { PageSpinner } from "@/components/PageSpinner";
import { PlayerAvatar } from "@/components/PlayerAvatar";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

const GOOGLE_RESULT: Record<string, () => void> = {
  linked: () => toast.success("Google account connected"),
  taken: () => toast.error("That Google account is already used by another player"),
  error: () => toast.error("Connecting Google failed, please try again"),
};

function ProfileCard({ account }: { account: Account }) {
  const queryClient = useQueryClient();
  const [username, setUsername] = useState(account.username);
  const [email, setEmail] = useState(account.email ?? "");
  const changed = username !== account.username || email !== (account.email ?? "");
  const save = useMutation({
    mutationFn: () =>
      api<Account>("/api/auth/account", {
        method: "PATCH",
        body: { username, email: email || null },
      }),
    onSuccess: (updated) => {
      queryClient.setQueryData(keys.account, updated);
      queryClient.setQueryData<User | null>(keys.me, (me) => (me ? { ...me, username: updated.username } : me));
      toast.success("Profile updated");
    },
    onError: (error) => toast.error(error.message),
  });

  const onSubmit = (event: FormEvent) => {
    event.preventDefault();
    save.mutate();
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-lg font-semibold">
          <UserIcon className="size-5 text-primary" /> Profile
        </CardTitle>
        <CardDescription>Your username is what other players see. Your email stays private.</CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={onSubmit} className="flex flex-wrap items-start gap-4">
          <PlayerAvatar name={username || account.username} className="size-12 [&_*]:text-base" />
          <div className="grid min-w-56 flex-1 gap-4 sm:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="username">Username</Label>
              <Input
                id="username"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                minLength={3}
                maxLength={32}
                pattern="[A-Za-z0-9_.\-]+"
                title="Letters, numbers, dots, dashes and underscores"
                required
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="email">Email</Label>
              <Input
                id="email"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                autoComplete="email"
                placeholder="you@company.com"
              />
            </div>
            {!account.email && (
              <p className="text-sm text-muted-foreground sm:col-span-2">
                Add an email so you can reset your password if you forget it.
              </p>
            )}
            <div className="sm:col-span-2">
              <Button type="submit" className="h-9" disabled={save.isPending || !changed}>
                Save changes
              </Button>
            </div>
          </div>
        </form>
      </CardContent>
    </Card>
  );
}

function PasswordCard({ account }: { account: Account }) {
  const queryClient = useQueryClient();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const mismatch = confirm.length > 0 && next !== confirm;

  const save = useMutation({
    mutationFn: () =>
      api("/api/auth/password", {
        method: "PUT",
        body: { current_password: account.has_password ? current : null, new_password: next },
      }),
    onSuccess: () => {
      setCurrent("");
      setNext("");
      setConfirm("");
      void queryClient.invalidateQueries({ queryKey: keys.account });
      toast.success(account.has_password ? "Password changed. Other devices were signed out." : "Password set");
    },
    onError: (error) => toast.error(error.message),
  });

  const onSubmit = (event: FormEvent) => {
    event.preventDefault();
    if (!mismatch) save.mutate();
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-lg font-semibold">
          <KeyRoundIcon className="size-5 text-primary" /> {account.has_password ? "Change password" : "Set a password"}
        </CardTitle>
        <CardDescription>
          {account.has_password
            ? "Changing your password signs you out on all other devices."
            : "You sign in with Google. Add a password to also sign in with your username."}
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={onSubmit} className="grid gap-4 sm:grid-cols-2">
          {account.has_password && (
            <div className="space-y-2 sm:col-span-2">
              <Label htmlFor="current-password">Current password</Label>
              <Input
                id="current-password"
                type="password"
                autoComplete="current-password"
                value={current}
                onChange={(e) => setCurrent(e.target.value)}
                required
              />
            </div>
          )}
          <div className="space-y-2">
            <Label htmlFor="new-password">New password</Label>
            <Input
              id="new-password"
              type="password"
              autoComplete="new-password"
              minLength={8}
              value={next}
              onChange={(e) => setNext(e.target.value)}
              required
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="confirm-password">Repeat new password</Label>
            <Input
              id="confirm-password"
              type="password"
              autoComplete="new-password"
              minLength={8}
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
              aria-invalid={mismatch}
              required
            />
            {mismatch && <p className="text-xs text-destructive">Passwords don't match</p>}
          </div>
          <div className="sm:col-span-2">
            <Button type="submit" className="h-9" disabled={save.isPending || mismatch}>
              {account.has_password ? "Change password" : "Set password"}
            </Button>
          </div>
        </form>
      </CardContent>
    </Card>
  );
}

function SignInMethodsCard({ account }: { account: Account }) {
  const queryClient = useQueryClient();
  const { data: providers } = useProviders();
  const unlink = useMutation({
    mutationFn: () => api("/api/auth/google", { method: "DELETE" }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: keys.account });
      toast.success("Google account disconnected");
    },
    onError: (error) => toast.error(error.message),
  });

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-lg font-semibold">Sign-in methods</CardTitle>
        <CardDescription>
          A connected Google account also works as a backup if you forget your password.
        </CardDescription>
      </CardHeader>
      <CardContent className="divide-y">
        <div className="flex items-center justify-between gap-4 py-3">
          <span className="flex items-center gap-3">
            <span className="flex size-9 items-center justify-center rounded-md bg-muted">
              <KeyRoundIcon className="size-4" />
            </span>
            <span>
              <span className="block font-medium">Username &amp; password</span>
              <span className="text-sm text-muted-foreground">{account.username}</span>
            </span>
          </span>
          {account.has_password ? (
            <Badge className="gap-1 bg-safe text-safe-foreground">
              <CheckCircle2Icon className="size-3" /> Enabled
            </Badge>
          ) : (
            <Badge variant="outline">Not set</Badge>
          )}
        </div>
        <div className="flex flex-wrap items-center justify-between gap-4 py-3">
          <span className="flex items-center gap-3">
            <span className="flex size-9 items-center justify-center rounded-md bg-muted">
              <GoogleIcon />
            </span>
            <span>
              <span className="block font-medium">Google</span>
              <span className="text-sm text-muted-foreground">
                {account.google_linked
                  ? (account.google_email ?? "Connected")
                  : providers?.google
                    ? "Not connected"
                    : "Not set up on this server yet"}
              </span>
            </span>
          </span>
          {account.google_linked ? (
            <Button
              variant="outline"
              size="sm"
              disabled={!account.has_password || unlink.isPending}
              title={account.has_password ? undefined : "Set a password first"}
              onClick={() => unlink.mutate()}
            >
              Disconnect
            </Button>
          ) : providers?.google ? (
            <Button variant="outline" size="sm" asChild>
              <a href="/api/auth/google/login?link=1">Connect</a>
            </Button>
          ) : (
            <Button variant="outline" size="sm" disabled>
              Connect
            </Button>
          )}
        </div>
      </CardContent>
    </Card>
  );
}

export function SettingsPage() {
  const { data: account, isPending } = useAccount();
  const [params, setParams] = useSearchParams();

  useEffect(() => {
    const result = params.get("google");
    if (result) {
      GOOGLE_RESULT[result]?.();
      setParams({}, { replace: true });
    }
  }, [params, setParams]);

  if (isPending || !account) return <PageSpinner />;

  return (
    <div className="mx-auto max-w-2xl space-y-6">
      <div>
        <h1 className="text-3xl font-bold">Settings</h1>
        <p className="text-muted-foreground">Manage your profile and how you sign in.</p>
      </div>
      <ProfileCard key={`${account.username}|${account.email}`} account={account} />
      <PasswordCard account={account} />
      <SignInMethodsCard account={account} />
    </div>
  );
}
