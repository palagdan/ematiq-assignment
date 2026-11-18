import { toast } from "sonner";

export async function copyCode(code: string): Promise<void> {
  await navigator.clipboard.writeText(code);
  toast.success(`Room code ${code} copied`);
}

export async function copyInvite(code: string): Promise<void> {
  await navigator.clipboard.writeText(`${window.location.origin}/r/${code}`);
  toast.success("Invite link copied");
}
