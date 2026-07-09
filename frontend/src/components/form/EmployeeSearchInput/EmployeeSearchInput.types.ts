import { Empleado } from "@/types/empleado";

export interface EmployeeSearchInputProps {
  label?: string;
  placeholder?: string;
  value?: Empleado | null;
  onChange: (employee: Empleado | null) => void;
  error?: boolean;
  hint?: string;
  disabled?: boolean;
  required?: boolean;
  name?: string;
  includeInactive?: boolean;
}

export interface EmployeeSearchState {
  searchTerm: string;
  results: Empleado[];
  isOpen: boolean;
  isLoading: boolean;
  selectedEmployee: Empleado | null;
}
