import { useMutation, useQueryClient } from "@tanstack/react-query";
import { AlertCircleIcon } from "lucide-react";
import { type FormEvent, useState } from "react";
import { Link, Navigate, useNavigate, useSearchParams } from "react-router-dom";
import { api } from "@/api/client";
import { keys, useMe, useProviders } from "@/api/hooks";
import type { User } from "@/api/types";
import { GoogleIcon } from "@/components/GoogleIcon";
import { LogoMark } from "@/components/Logo";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Separator } from "@/components/ui/separator";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";

type Mode = "login" | "register";

export function LoginPage() {
  const [mode, setMode] = useState<Mode>("login");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [email, setEmail] = useState("");
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { data: me } = useMe();
  const { data: providers } = useProviders();
  const next = params.get("next") ?? "/";

  const submit = useMutation({
    mutationFn: () =>
      api<User>(`/api/auth/${mode}`, {
        method: "POST",
        body: mode === "register" ? { username, email, password } : { username, password },
      }),
    onSuccess: (user) => {
      queryClient.setQueryData(keys.me, user);
      navigate(next, { replace: true });
    },
  });

  if (me) return <Navigate to={next} replace />;

  const onSubmit = (event: FormEvent) => {
    event.preventDefault();
    submit.mutate();
  };

  const error = submit.error?.message ?? (params.get("error") === "google" ? "Google sign-in failed." : null);

  return (
    <div className="mx-auto max-w-sm pt-6">
      <Card className="shadow-lg shadow-[#0f1530]/5">
        <CardHeader className="items-center text-center">
          <LogoMark className="mx-auto mb-2 size-12 rounded-xl [&_svg]:size-6" />
          <CardTitle className="text-2xl font-semibold">
            {mode === "login" ? "Welcome back" : "Join the lunch crew"}
          </CardTitle>
          <CardDescription>Play a quick game and see who picks up the bill.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-5">
          <Tabs
            value={mode}
            onValueChange={(value) => {
              setMode(value as Mode);
              submit.reset();
            }}
          >
            <TabsList className="w-full">
              <TabsTrigger value="login">Log in</TabsTrigger>
              <TabsTrigger value="register">Create account</TabsTrigger>
            </TabsList>
          </Tabs>

          <form onSubmit={onSubmit} className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="username">Username</Label>
              <Input
                id="username"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                autoComplete="username"
                minLength={3}
                maxLength={32}
                required
              />
            </div>
            {mode === "register" && (
              <div className="space-y-2">
                <Label htmlFor="email">Email</Label>
                <Input
                  id="email"
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  autoComplete="email"
                  required
                />
                <p className="text-xs text-muted-foreground">Only used to reset your password.</p>
              </div>
            )}
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <Label htmlFor="password">Password</Label>
                {mode === "login" && (
                  <Link to="/forgot-password" className="text-xs font-medium text-primary hover:underline">
                    Forgot password?
                  </Link>
                )}
              </div>
              <Input
                id="password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete={mode === "login" ? "current-password" : "new-password"}
                minLength={8}
                required
              />
              {mode === "register" && (
                <p className="text-xs text-muted-foreground">At least 8 characters.</p>
              )}
            </div>
            {error && (
              <Alert variant="destructive">
                <AlertCircleIcon />
                <AlertDescription>{error}</AlertDescription>
              </Alert>
            )}
            <Button type="submit" size="lg" className="h-10 w-full" disabled={submit.isPending}>
              {mode === "login" ? "Log in" : "Create account"}
            </Button>
          </form>

          <div className="flex items-center gap-3 text-xs text-muted-foreground">
            <Separator className="flex-1" />
            or
            <Separator className="flex-1" />
          </div>
          {providers?.google ? (
            <Button variant="outline" size="lg" className="h-10 w-full" asChild>
              <a href="/api/auth/google/login">
                <GoogleIcon />
                Continue with Google
              </a>
            </Button>
          ) : (
            <div className="space-y-1.5">
              <Button variant="outline" size="lg" className="h-10 w-full" disabled>
                <GoogleIcon />
                Continue with Google
              </Button>
              <p className="text-center text-xs text-muted-foreground">
                Google sign-in isn't set up on this server yet.
              </p>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
