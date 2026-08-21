import "@/App.css";
import { useEffect, useState } from "react";
import axios from "axios";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import { Toaster } from "@/components/ui/sonner";
import Dashboard from "@/pages/Dashboard";
import Invoices from "@/pages/Invoices";
import Expenses from "@/pages/Expenses";
import BankStatements from "@/pages/BankStatements";
import Transactions from "@/pages/Transactions";
import TaxPrep from "@/pages/TaxPrep";
import TidyUp from "@/pages/TidyUp";
import Mileage from "@/pages/Mileage";
import Layout from "@/components/Layout";
import Login from "@/pages/Login";

const API = `${process.env.REACT_APP_BACKEND_URL || ""}/api`;

function App() {
  const [user, setUser] = useState(null);
  const [checking, setChecking] = useState(true);

  useEffect(() => {
    const checkSession = async () => {
      try {
        const response = await axios.get(`${API}/auth/me`);
        sessionStorage.setItem("accounts_csrf", response.data.csrf_token);
        setUser(response.data);
      } catch {
        sessionStorage.removeItem("accounts_csrf");
        setUser(null);
      } finally {
        setChecking(false);
      }
    };
    const expired = () => setUser(null);
    window.addEventListener("accounts-session-expired", expired);
    checkSession();
    return () => window.removeEventListener("accounts-session-expired", expired);
  }, []);

  const signOut = async () => {
    try { await axios.post(`${API}/auth/logout`); } catch { /* clear the local session regardless */ }
    sessionStorage.removeItem("accounts_csrf");
    setUser(null);
  };

  if (checking) {
    return <div className="min-h-screen bg-[#f7f5f1] flex items-center justify-center text-stone-500">Opening your accounts…</div>;
  }

  if (!user) return <Login onSignedIn={setUser} />;

  return (
    <div className="App">
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<Layout user={user} onSignOut={signOut} />}>
            <Route index element={<Dashboard />} />
            <Route path="invoices" element={<Invoices />} />
            <Route path="expenses" element={<Expenses />} />
            <Route path="bank-statements" element={<BankStatements />} />
            <Route path="transactions" element={<Transactions />} />
            <Route path="tax-prep" element={<TaxPrep />} />
            <Route path="tidy-up" element={<TidyUp />} />
            <Route path="mileage" element={<Mileage />} />
          </Route>
        </Routes>
      </BrowserRouter>
      <Toaster position="top-right" />
    </div>
  );
}

export default App;
