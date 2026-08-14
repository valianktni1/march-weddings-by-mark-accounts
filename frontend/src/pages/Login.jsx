import { useState } from "react";
import axios from "axios";
import { Camera, LockKeyhole } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

const API = `${process.env.REACT_APP_BACKEND_URL || ""}/api`;

export default function Login({ onSignedIn }) {
  const [email, setEmail] = useState("mark@perfectweddingsbymark.uk");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async (event) => {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const response = await axios.post(`${API}/auth/login`, { email, password });
      sessionStorage.setItem("accounts_csrf", response.data.csrf_token);
      onSignedIn(response.data);
    } catch (requestError) {
      setError(requestError.response?.data?.detail || "Unable to sign in. Please try again.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className="min-h-screen bg-[#f7f5f1] px-5 py-10 flex items-center justify-center">
      <section className="w-full max-w-md rounded-2xl border border-stone-200 bg-white p-7 sm:p-9 shadow-xl shadow-stone-900/5">
        <div className="flex items-center gap-3 mb-8">
          <div className="w-12 h-12 rounded-xl bg-[#C7A76D] flex items-center justify-center">
            <Camera className="w-6 h-6 text-white" />
          </div>
          <div>
            <h1 className="text-2xl font-semibold text-stone-900">Weddings by Mark</h1>
            <p className="text-sm text-stone-500">Secure financial manager</p>
          </div>
        </div>

        <div className="mb-7">
          <div className="inline-flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.16em] text-[#9b7a43]">
            <LockKeyhole className="w-4 h-4" /> Private accounts
          </div>
          <h2 className="mt-3 text-3xl font-semibold text-stone-900">Welcome back, Mark</h2>
          <p className="mt-2 text-sm leading-6 text-stone-500">Sign in to view invoices, expenses and tax records.</p>
        </div>

        <form onSubmit={submit} className="space-y-5">
          <div className="space-y-2">
            <Label htmlFor="email">Email address</Label>
            <Input id="email" type="email" autoComplete="username" value={email} onChange={(e) => setEmail(e.target.value)} required />
          </div>
          <div className="space-y-2">
            <Label htmlFor="password">Password</Label>
            <Input id="password" type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} required autoFocus />
          </div>
          {error && <p className="rounded-lg bg-rose-50 px-4 py-3 text-sm text-rose-700" role="alert">{error}</p>}
          <Button type="submit" disabled={busy} className="w-full bg-[#C7A76D] hover:bg-[#b6945c] text-white h-11">
            {busy ? "Signing in…" : "Sign in securely"}
          </Button>
        </form>
      </section>
    </main>
  );
}
