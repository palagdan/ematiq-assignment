import { useQueryClient } from "@tanstack/react-query";
import { ChevronDownIcon, Gamepad2Icon, HistoryIcon, LogOutIcon, SettingsIcon, SwordsIcon } from "lucide-react";
import type { ReactNode } from "react";
import { Link, NavLink, useLocation, useNavigate } from "react-router-dom";
import { api } from "@/api/client";
import { useCurrentRoom, useMe } from "@/api/hooks";
import type { Room, User } from "@/api/types";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { cn } from "@/lib/utils";
import { Logo } from "./Logo";
import { PlayerAvatar } from "./PlayerAvatar";

function NavItem({ to, icon, children }: { to: string; icon: ReactNode; children: ReactNode }) {
  return (
    <NavLink
      to={to}
      end
      className={({ isActive }) =>
        cn(
          "inline-flex h-9 items-center gap-2 rounded-lg px-3 text-sm font-medium text-muted-foreground transition-colors hover:bg-accent hover:text-foreground",
          isActive && "bg-accent text-foreground",
        )
      }
    >
      {icon}
      <span className="hidden sm:inline">{children}</span>
    </NavLink>
  );
}

function BackToGame({ room, me }: { room: Room; me: User }) {
  const myTurn = room.status === "playing" && room.current_player_id === me.id;
  return (
    <Link
      to={`/r/${room.code}`}
      className={cn(
        "inline-flex h-9 items-center gap-2 rounded-full px-3 text-sm font-semibold transition-colors",
        myTurn
          ? "animate-pulse bg-primary text-primary-foreground"
          : "bg-safe-soft text-safe-strong ring-1 ring-safe/50 hover:bg-safe/20",
      )}
    >
      <Gamepad2Icon className="size-4" />
      <span className="hidden sm:inline">{myTurn ? "Your turn!" : "Back to game"}</span>
      <span className="font-mono tracking-widest">{room.code}</span>
    </Link>
  );
}

export function Layout({ children }: { children: ReactNode }) {
  const { data: me } = useMe();
  const { data: currentRoom } = useCurrentRoom();
  const { pathname } = useLocation();
  const queryClient = useQueryClient();
  const navigate = useNavigate();

  const logout = async () => {
    await api("/api/auth/logout", { method: "POST" });
    queryClient.clear();
    navigate("/login");
  };

  return (
    <div className="min-h-screen bg-background">
      <header className="sticky top-0 z-40 border-b bg-card/85 backdrop-blur-md">
        <div className="mx-auto flex h-16 max-w-5xl items-center justify-between gap-4 px-4">
          <Link to="/" aria-label="Lunch Roulette home">
            <Logo />
          </Link>
          {me && (
            <nav className="flex items-center gap-1">
              {currentRoom && pathname !== `/r/${currentRoom.code}` && (
                <span className="mr-1">
                  <BackToGame room={currentRoom} me={me} />
                </span>
              )}
              <NavItem to="/" icon={<SwordsIcon className="size-4" />}>
                Play
              </NavItem>
              <NavItem to="/history" icon={<HistoryIcon className="size-4" />}>
                History
              </NavItem>
              <div className="ml-2 border-l pl-3">
                <DropdownMenu>
                  <DropdownMenuTrigger
                    className="flex items-center gap-2 rounded-lg p-1 pr-2 outline-none hover:bg-accent focus-visible:ring-2 focus-visible:ring-ring"
                    aria-label="Account menu"
                  >
                    <PlayerAvatar name={me.username} />
                    <span className="hidden text-sm font-medium md:inline">{me.username}</span>
                    <ChevronDownIcon className="size-4 text-muted-foreground" />
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="end" className="w-52">
                    <DropdownMenuLabel className="font-normal">
                      <p className="text-xs text-muted-foreground">Signed in as</p>
                      <p className="truncate font-medium">{me.username}</p>
                    </DropdownMenuLabel>
                    <DropdownMenuSeparator />
                    <DropdownMenuItem onSelect={() => navigate("/settings")}>
                      <SettingsIcon /> Settings
                    </DropdownMenuItem>
                    <DropdownMenuSeparator />
                    <DropdownMenuItem variant="destructive" onSelect={logout}>
                      <LogOutIcon /> Log out
                    </DropdownMenuItem>
                  </DropdownMenuContent>
                </DropdownMenu>
              </div>
            </nav>
          )}
        </div>
      </header>
      <main className="mx-auto max-w-5xl px-4 py-8">{children}</main>
    </div>
  );
}
