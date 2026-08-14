// UK date format helper (DD/MM/YYYY)
export const formatDateUK = (dateString) => {
  if (!dateString) return '';
  
  // If already in DD/MM/YYYY format
  if (/^\d{2}\/\d{2}\/\d{4}$/.test(dateString)) {
    return dateString;
  }
  
  try {
    const date = new Date(dateString);
    if (isNaN(date.getTime())) return dateString;
    
    const day = String(date.getDate()).padStart(2, '0');
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const year = date.getFullYear();
    return `${day}/${month}/${year}`;
  } catch {
    return dateString;
  }
};

// Parse UK date string to Date object
export const parseUKDate = (dateString) => {
  if (!dateString) return new Date();
  
  const parts = dateString.split('/');
  if (parts.length === 3) {
    return new Date(parts[2], parts[1] - 1, parts[0]);
  }
  return new Date(dateString);
};

// Format currency as GBP
export const formatCurrency = (amount) => {
  return new Intl.NumberFormat('en-GB', {
    style: 'currency',
    currency: 'GBP',
    minimumFractionDigits: 2
  }).format(amount || 0);
};

// Get current UK tax year
export const getCurrentTaxYear = () => {
  const now = new Date();
  const month = now.getMonth() + 1;
  const day = now.getDate();
  const year = now.getFullYear();
  
  // UK tax year runs from 6th April to 5th April
  if (month < 4 || (month === 4 && day < 6)) {
    return `${year - 1}-${String(year).slice(-2)}`;
  }
  return `${year}-${String(year + 1).slice(-2)}`;
};

// Convert date to YYYY-MM-DD for input fields
export const toInputDate = (ukDateString) => {
  if (!ukDateString) return '';
  
  const parts = ukDateString.split('/');
  if (parts.length === 3) {
    return `${parts[2]}-${parts[1]}-${parts[0]}`;
  }
  return ukDateString;
};

// Convert YYYY-MM-DD to UK format
export const fromInputDate = (inputDate) => {
  if (!inputDate) return '';
  
  const parts = inputDate.split('-');
  if (parts.length === 3) {
    return `${parts[2]}/${parts[1]}/${parts[0]}`;
  }
  return inputDate;
};
