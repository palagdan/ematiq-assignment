import { useMutation } from "@tanstack/react-query";
import { ArrowLeftIcon, MailCheckIcon } from "lucide-react";
import { type FormEvent, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "@/api/client";
import { LogoMark } from "@/components/Logo";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

export function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const send = useMutation({
    mutationFn: () => api("/api/auth/password/forgot", { method: "POST", body: { email } }),
  });

  const onSubmit = (event: FormEvent) => {
    event.preventDefault();
    send.mutate();
  };

  return (
    <div className="mx-auto max-w-sm pt-6">
      <Card className="shadow-lg shadow-[#0f1530]/5">
        <CardHeader className="items-center text-center">
          <LogoMark className="mx-auto mb-2 size-12 rounded-xl [&_svg]:size-6" />
          <CardTitle className="text-2xl font-semibold">Forgot your password?</CardTitle>
          <CardDescription>Enter the email you signed up with and we'll send you a reset link.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-5">
          {send.isSuccess ? (
            <div className="space-y-2 rounded-lg bg-safe-soft p-4 text-center">
              <MailCheckIcon className="mx-auto size-8 text-safe-strong" />
              <p className="font-medium">Check your inbox</p>
              <p className="text-sm text-muted-foreground">
                If an account uses <span className="font-medium text-foreground">{email}</span>, a reset link is on
                its way. It works once and expires in 30 minutes.
              </p>
            </div>
          ) : (
            <form onSubmit={onSubmit} className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="email">Email</Label>
                <Input
                  id="email"
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  autoComplete="email"
                  required
                  autoFocus
                />
              </div>
              {send.error && <p className="text-sm text-destructive">{send.error.message}</p>}
              <Button type="submit" size="lg" className="h-10 w-full" disabled={send.isPending}>
                Send reset link
              </Button>
            </form>
          )}
          <Button variant="ghost" className="w-full" asChild>
            <Link to="/login">
              <ArrowLeftIcon /> Back to sign in
            </Link>
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}
