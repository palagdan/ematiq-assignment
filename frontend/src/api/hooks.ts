import {
  type QueryClient,
  useInfiniteQuery,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { toast } from "sonner";
import { ApiError, api } from "./client";
import type { Account, Currency, DecimalString, HistoryPage, Providers, Room, User } from "./types";

export const keys = {
  me: ["me"] as const,
  account: ["account"] as const,
  providers: ["providers"] as const,
  rates: ["rates"] as const,
  room: (code: string) => ["room", code] as const,
  currentRoom: ["current-room"] as const,
  history: (mine: boolean) => ["history", { mine }] as const,
};

export function useMe() {
  return useQuery({
    queryKey: keys.me,
    queryFn: async () => {
      try {
        return await api<User>("/api/auth/me");
      } catch (error) {
        if (error instanceof ApiError && error.status === 401) return null;
        throw error;
      }
    },
    staleTime: Infinity,
  });
}

export function useAccount() {
  return useQuery({ queryKey: keys.account, queryFn: () => api<Account>("/api/auth/account") });
}

export function useProviders() {
  return useQuery({
    queryKey: keys.providers,
    queryFn: () => api<Providers>("/api/auth/providers"),
    staleTime: Infinity,
  });
}

export function useRates(enabled: boolean) {
  return useQuery({
    queryKey: keys.rates,
    queryFn: () => api<Record<Currency, DecimalString>>("/api/rates"),
    enabled,
    staleTime: 60_000,
  });
}

/** Stores a room snapshot unless the cache already holds a newer one. */
export function acceptRoom(queryClient: QueryClient, room: Room): void {
  queryClient.setQueryData<Room>(keys.room(room.code), (previous) =>
    !previous || room.version >= previous.version ? room : previous,
  );
  // Keep "your current game" in sync, e.g. drop it once the game is over.
  const current = queryClient.getQueryData<Room | null>(keys.currentRoom);
  if (current?.code === room.code && room.version >= current.version) {
    queryClient.setQueryData(keys.currentRoom, room.status === "finished" ? null : room);
  }
}

/** The one active (lobby or playing) room the user is in, or null. */
export function useCurrentRoom() {
  return useQuery({
    queryKey: keys.currentRoom,
    queryFn: () => api<Room | null>("/api/rooms/current"),
    refetchOnWindowFocus: true,
    // There's no socket outside the room page, so poll during a game to catch "your turn".
    refetchInterval: (query) => (query.state.data?.status === "playing" ? 4000 : false),
  });
}

export function useRoom(code: string) {
  return useQuery({
    queryKey: keys.room(code),
    queryFn: () => api<Room>(`/api/rooms/${code}`),
    retry: (count, error) => !(error instanceof ApiError && error.status === 404) && count < 2,
    // The WebSocket keeps the cache fresh.
    staleTime: Infinity,
  });
}

export function useRoomAction<TVariables = void>(fn: (variables: TVariables) => Promise<Room>) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: fn,
    onSuccess: (room) => {
      acceptRoom(queryClient, room);
      void queryClient.invalidateQueries({ queryKey: keys.currentRoom });
    },
    onError: (error) => toast.error(error.message),
  });
}

const PAGE_SIZE = 20;

export function useHistory(mine: boolean) {
  return useInfiniteQuery({
    queryKey: keys.history(mine),
    queryFn: ({ pageParam }) =>
      api<HistoryPage>(`/api/history?mine=${mine}&offset=${pageParam}&limit=${PAGE_SIZE}`),
    initialPageParam: 0,
    getNextPageParam: (last, pages) => (last.has_more ? pages.length * PAGE_SIZE : undefined),
  });
}
