import { useEffect, useRef, useState } from "react";
import { Empleado } from "@/types/empleado";
import { searchEmpleados } from "@/services/empleado.service";
import { getAvatarUrl, preloadAvatars } from "@/utils/avatar";
import { EMPLOYEE_SEARCH_CONFIG } from "./EmployeeSearchInput.utils";
import { logDevelopmentError } from "@/lib/environment";

interface UseEmployeeSearchParams {
  value?: Empleado | null;
  includeInactive?: boolean;
}

export const useEmployeeSearch = (
  params: UseEmployeeSearchParams = {},
) => {
  const { value, includeInactive = false } = params;
  const shouldIncludeInactive = Boolean(includeInactive);
  const [searchTerm, setSearchTerm] = useState("");
  const [results, setResults] = useState<Empleado[]>([]);
  const [isOpen, setIsOpen] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [selectedEmployee, setSelectedEmployee] = useState<Empleado | null>(
    value || null,
  );
  const wrapperRef = useRef<HTMLDivElement>(null);
  const searchTimeoutRef = useRef<NodeJS.Timeout | undefined>(undefined);

  // Close dropdown when clicking outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (
        wrapperRef.current &&
        !wrapperRef.current.contains(event.target as Node)
      ) {
        setIsOpen(false);
      }
    };

    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  // Update selected employee when value prop changes
  useEffect(() => {
    setSelectedEmployee(value || null);
  }, [value]);

  // Handle search with debounce
  useEffect(() => {
    if (searchTimeoutRef.current) {
      clearTimeout(searchTimeoutRef.current);
    }

    if (searchTerm.length >= EMPLOYEE_SEARCH_CONFIG.minSearchLength) {
      setIsLoading(true);
      searchTimeoutRef.current = setTimeout(async () => {
        try {
          const data = await searchEmpleados(searchTerm, shouldIncludeInactive);
          setResults(data);
          setIsOpen(true);

          // Precargar imágenes
          const imageUrls = data
            .map((emp) => emp.link_foto)
            .filter(Boolean)
            .map((foto) => getAvatarUrl(foto));

          if (imageUrls.length > 0) {
            preloadAvatars(imageUrls);
          }
        } catch (error) {
          logDevelopmentError("Error searching employees:", error);
          setResults([]);
        } finally {
          setIsLoading(false);
        }
      }, EMPLOYEE_SEARCH_CONFIG.debounceDelay);
    } else {
      setResults([]);
      setIsOpen(false);
    }

    return () => {
      if (searchTimeoutRef.current) {
        clearTimeout(searchTimeoutRef.current);
      }
    };
  }, [searchTerm, shouldIncludeInactive]);

  const handleSelect = (
    employee: Empleado,
    onChange: (e: Empleado | null) => void,
  ) => {
    setSelectedEmployee(employee);
    onChange(employee);
    setSearchTerm("");
    setIsOpen(false);
    setResults([]);
  };

  const handleClear = (onChange: (e: Empleado | null) => void) => {
    setSelectedEmployee(null);
    onChange(null);
    setSearchTerm("");
    setResults([]);
  };

  const handleInputChange = (
    e: React.ChangeEvent<HTMLInputElement>,
    onChange: (e: Empleado | null) => void,
  ) => {
    setSearchTerm(e.target.value);
    if (selectedEmployee) {
      setSelectedEmployee(null);
      onChange(null);
    }
  };

  return {
    searchTerm,
    results,
    isOpen,
    isLoading,
    selectedEmployee,
    wrapperRef,
    setSelectedEmployee,
    handleSelect,
    handleClear,
    handleInputChange,
  };
};
