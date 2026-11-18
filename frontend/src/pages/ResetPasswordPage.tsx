import { useMutation, useQueryClient } from "@tanstack/react-query";
import { AlertCircleIcon } from "lucide-react";
import { type FormEvent, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { api } from "@/api/client";
import { keys } from "@/api/hooks";
import type { User } from "@/api/types";
import { LogoMark } from "@/components/Logo";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

export function ResetPasswordPage() {
  const [params] = useSearchParams();
  const token = params.get("token") ?? "";
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const mismatch = confirm.length > 0 && password !== confirm;
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const reset = useMutation({
    mutationFn: () =>
      api<User>("/api/auth/password/reset", { method: "POST", body: { token, new_password: password } }),
    onSuccess: (user) => {
      queryClient.clear();
      queryClient.setQueryData(keys.me, user);
      toast.success("Password changed. You're signed in.");
      navigate("/", { replace: true });
    },
  });

  const onSubmit = (event: FormEvent) => {
    event.preventDefault();
    if (!mismatch) reset.mutate();
  };

  return (
    <div className="mx-auto max-w-sm pt-6">
      <Card className="shadow-lg shadow-[#0f1530]/5">
        <CardHeader className="items-center text-center">
          <LogoMark className="mx-auto mb-2 size-12 rounded-xl [&_svg]:size-6" />
          <CardTitle className="text-2xl font-semibold">Choose a new password</CardTitle>
          <CardDescription>You'll be signed out on all other devices.</CardDescription>
        </CardHeader>
        <CardContent>
          {!token ? (
            <Alert variant="destructive">
              <AlertCircleIcon />
              <AlertDescription>
                This link is missing its token. <Link to="/forgot-password" className="underline">Request a new one</Link>.
              </AlertDescription>
            </Alert>
          ) : (
            <form onSubmit={onSubmit} className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="new-password">New password</Label>
                <Input
                  id="new-password"
                  type="password"
                  autoComplete="new-password"
                  minLength={8}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                  autoFocus
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
              {reset.error && (
                <Alert variant="destructive">
                  <AlertCircleIcon />
                  <AlertDescription>
                    {reset.error.message}{" "}
                    <Link to="/forgot-password" className="underline">Send a new link</Link>
                  </AlertDescription>
                </Alert>
              )}
              <Button type="submit" size="lg" className="h-10 w-full" disabled={reset.isPending || mismatch}>
                Save new password
              </Button>
            </form>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
