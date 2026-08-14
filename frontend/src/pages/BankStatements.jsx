import { useState, useEffect, useCallback } from "react";
import axios from "axios";
import { toast } from "sonner";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Upload, FileText, RefreshCw, CheckCircle, Clock, AlertCircle, Trash2 } from "lucide-react";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

export const BankStatements = () => {
  const [statements, setStatements] = useState([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [parsing, setParsing] = useState(null);
  const [deleting, setDeleting] = useState(false);

  const fetchStatements = useCallback(async () => {
    setLoading(true);
    try {
      const response = await axios.get(`${API}/bank-statements`);
      setStatements(response.data);
    } catch (error) {
      console.error("Failed to fetch statements:", error);
      toast.error("Failed to load bank statements");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchStatements();
  }, [fetchStatements]);

  const handleUpload = async (event) => {
    const file = event.target.files?.[0];
    if (!file) return;

    setUploading(true);
    try {
      const formData = new FormData();
      formData.append("file", file);
      
      const response = await axios.post(`${API}/bank-statements/upload`, formData);
      toast.success("Bank statement uploaded successfully!");
      fetchStatements();
      
      // Auto-parse the statement
      handleParse(response.data.id);
    } catch (error) {
      console.error("Upload failed:", error);
      toast.error("Failed to upload bank statement");
    } finally {
      setUploading(false);
      event.target.value = '';
    }
  };

  const handleParse = async (statementId) => {
    setParsing(statementId);
    try {
      await axios.post(`${API}/bank-statements/${statementId}/parse`);
      toast.info("Parsing started — extracting transactions...");
      
      // Poll for status
      const pollInterval = setInterval(async () => {
        try {
          const statusRes = await axios.get(`${API}/bank-statements/${statementId}/parse-status`);
          const { parse_status, transaction_count, parse_error } = statusRes.data;
          
          if (parse_status === "success") {
            clearInterval(pollInterval);
            setParsing(null);
            toast.success(`Extracted ${transaction_count} transactions!`);
            fetchStatements();
          } else if (parse_status === "error") {
            clearInterval(pollInterval);
            setParsing(null);
            toast.error("Failed to parse: " + (parse_error || "Unknown error"));
            fetchStatements();
          }
          // If still "processing", keep polling
        } catch (pollErr) {
          console.error("Poll error:", pollErr);
        }
      }, 3000);
      
      // Safety timeout: stop polling after 5 minutes
      setTimeout(() => {
        clearInterval(pollInterval);
        if (parsing === statementId) {
          setParsing(null);
          toast.error("Parsing timed out. Please try again.");
          fetchStatements();
        }
      }, 300000);
      
    } catch (error) {
      console.error("Parse failed:", error);
      toast.error("Failed to start parsing: " + (error.response?.data?.detail || error.message));
      setParsing(null);
    }
  };

  const formatDate = (dateStr) => {
    try {
      return new Date(dateStr).toLocaleDateString('en-GB', {
        day: '2-digit',
        month: '2-digit',
        year: 'numeric'
      });
    } catch {
      return dateStr;
    }
  };

  const handleDeleteAll = async () => {
    if (!window.confirm("This will delete ALL bank statements and ALL bank transactions. Your manual expenses and invoices will NOT be affected.\n\nAre you sure?")) return;
    setDeleting(true);
    try {
      const res = await axios.delete(`${API}/bank-statements/all`);
      toast.success(`Deleted ${res.data.statements_deleted} statements and ${res.data.transactions_deleted} transactions`);
      fetchStatements();
    } catch { toast.error("Failed to delete bank data"); }
    finally { setDeleting(false); }
  };

  return (
    <div className="space-y-6 animate-fade-in" data-testid="bank-statements-page">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
        <div>
          <h1 className="text-3xl font-medium tracking-tight text-stone-900" style={{ fontFamily: 'Playfair Display, serif' }}>
            Bank Statements
          </h1>
          <p className="text-stone-500 mt-1">Upload and parse your Tide bank statements</p>
        </div>
        
        <div className="flex items-center gap-3">
          {statements.length > 0 && (
            <Button
              variant="outline"
              disabled={deleting}
              onClick={handleDeleteAll}
              className="border-rose-300 text-rose-600 hover:bg-rose-50 rounded-sm"
              data-testid="delete-all-bank-btn"
            >
              <Trash2 className="w-4 h-4 mr-2" />
              {deleting ? "Deleting..." : "Delete All Bank Data"}
            </Button>
          )}
          <label>
            <Button 
              asChild
              disabled={uploading}
              className="bg-[#C7A76D] text-white hover:bg-[#B8985E] rounded-sm cursor-pointer"
              data-testid="upload-statement-btn"
            >
              <span>
                {uploading ? (
                  <RefreshCw className="w-4 h-4 mr-2 animate-spin" />
                ) : (
                  <Upload className="w-4 h-4 mr-2" />
                )}
                Upload Statement
              </span>
            </Button>
            <Input
              type="file"
              accept=".pdf,.csv,.jpg,.jpeg,.png"
              onChange={handleUpload}
              className="hidden"
              data-testid="statement-file-input"
            />
          </label>
        </div>
      </div>

      {/* Info Card */}
      <Card className="bg-emerald-50 border-emerald-100" data-testid="info-card">
        <CardContent className="py-4">
          <div className="flex items-start gap-3">
            <AlertCircle className="w-5 h-5 text-emerald-600 mt-0.5" />
            <div>
              <p className="text-sm font-medium text-emerald-800">Auto-Extraction with AI</p>
              <p className="text-sm text-emerald-700 mt-1">
                Upload your Tide bank statement PDF and we'll automatically extract all transactions.
                HMRC payments and transactions from MARK POWELL / MARK ADAM POWELL will be marked as 
                owner withdrawals and excluded from expense totals.
              </p>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Statements Table */}
      <Card className="bg-white border-stone-100 card-shadow" data-testid="statements-table-card">
        <CardHeader>
          <CardTitle className="text-lg" style={{ fontFamily: 'Playfair Display, serif' }}>
            Uploaded Statements
          </CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow className="border-stone-100">
                <TableHead className="text-stone-500">File Name</TableHead>
                <TableHead className="text-stone-500">Upload Date</TableHead>
                <TableHead className="text-stone-500">Status</TableHead>
                <TableHead className="text-stone-500">Transactions</TableHead>
                <TableHead className="text-right text-stone-500">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {loading ? (
                <TableRow>
                  <TableCell colSpan={5} className="text-center py-8 text-stone-400">
                    Loading...
                  </TableCell>
                </TableRow>
              ) : statements.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={5} className="text-center py-8 text-stone-400">
                    <div className="flex flex-col items-center gap-2">
                      <FileText className="w-8 h-8 text-stone-300" />
                      <p>No bank statements uploaded yet.</p>
                      <p className="text-xs">Upload a PDF, CSV, or image of your Tide statement.</p>
                    </div>
                  </TableCell>
                </TableRow>
              ) : (
                statements.map((statement) => (
                  <TableRow key={statement.id} className="border-stone-100" data-testid={`statement-row-${statement.id}`}>
                    <TableCell className="font-medium flex items-center gap-2">
                      <FileText className="w-4 h-4 text-stone-400" />
                      {statement.file_name}
                    </TableCell>
                    <TableCell className="font-mono text-sm">
                      {formatDate(statement.upload_date)}
                    </TableCell>
                    <TableCell>
                      {statement.processed ? (
                        <span className="inline-flex items-center gap-1 text-xs px-2 py-1 bg-emerald-50 text-emerald-700 rounded-sm">
                          <CheckCircle className="w-3 h-3" />
                          Processed
                        </span>
                      ) : statement.parse_status === "processing" || parsing === statement.id ? (
                        <span className="inline-flex items-center gap-1 text-xs px-2 py-1 bg-blue-50 text-blue-700 rounded-sm">
                          <RefreshCw className="w-3 h-3 animate-spin" />
                          Extracting...
                        </span>
                      ) : statement.parse_status === "error" ? (
                        <span className="inline-flex items-center gap-1 text-xs px-2 py-1 bg-red-50 text-red-700 rounded-sm" title={statement.parse_error || ""}>
                          <AlertCircle className="w-3 h-3" />
                          Failed
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1 text-xs px-2 py-1 bg-amber-50 text-amber-700 rounded-sm">
                          <Clock className="w-3 h-3" />
                          Pending
                        </span>
                      )}
                    </TableCell>
                    <TableCell className="font-mono">
                      {statement.transaction_count || 0}
                    </TableCell>
                    <TableCell className="text-right">
                      {!statement.processed && (
                        <Button
                          variant="outline"
                          size="sm"
                          disabled={parsing === statement.id || statement.parse_status === "processing"}
                          onClick={() => handleParse(statement.id)}
                          className="border-[#C7A76D] text-[#C7A76D] hover:bg-[#C7A76D]/10"
                          data-testid={`parse-statement-${statement.id}`}
                        >
                          {parsing === statement.id || statement.parse_status === "processing" ? (
                            <>
                              <RefreshCw className="w-3 h-3 mr-1 animate-spin" />
                              Parsing...
                            </>
                          ) : statement.parse_status === "error" ? (
                            "Retry Extract"
                          ) : (
                            "Extract Transactions"
                          )}
                        </Button>
                      )}
                    </TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
};

export default BankStatements;
