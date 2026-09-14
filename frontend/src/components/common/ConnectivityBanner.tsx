import { useQuery } from "@tanstack/react-query";
import { healthApi } from "@/api/health";
import { API_BASE_URL } from "@/api/client";

export function ConnectivityBanner() {
  const { error, isLoading } = useQuery({
    queryKey: ["health"],
    queryFn: healthApi.live,
    retry: 1,
    staleTime: 30000,
  });

  if (isLoading || !error) return null;

  return (
    <div className="border-b border-rose-200 bg-rose-50 px-4 py-2 text-center text-xs text-rose-700">
      Can't reach the backend at <span className="font-mono">{API_BASE_URL}</span>. Check it's running and{" "}
      <span className="font-mono">VITE_API_BASE_URL</span> is correct.
    </div>
  );
}
