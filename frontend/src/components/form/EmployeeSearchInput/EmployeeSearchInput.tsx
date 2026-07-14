import React from "react";
import { useEmployeeSearch } from "./EmployeeSearchInput.hooks";
import { EmployeeSearchInputProps } from "./EmployeeSearchInput.types";
import { getInputClasses } from "./EmployeeSearchInput.utils";
import { EmployeeSearchInputSelected } from "./EmployeeSearchInputSelected";
import { EmployeeSearchInputDropdown } from "./EmployeeSearchInputDropdown";

/**
 * Componente de búsqueda de empleados con dropdown y selección
 *
 * Features:
 * - Búsqueda con debounce (300ms)
 * - Precarga de imágenes
 * - Click outside para cerrar dropdown
 * - Estados: cargando, sin resultados, error
 * - Soporte para disabled y validación
 *
 * @example
 * ```tsx
 * <EmployeeSearchInput
 *   label="Responsable"
 *   value={selectedEmployee}
 *   onChange={(emp) => setSelectedEmployee(emp)}
 *   error={!!errors.responsable}
 *   hint="Busca por nombre, cédula..."
 * />
 * ```
 */
export const EmployeeSearchInput = React.forwardRef<
  HTMLDivElement,
  EmployeeSearchInputProps
>(
  (
    {
      label,
      placeholder = "Buscar empleado...",
      value,
      onChange,
      error = false,
      hint,
      disabled = false,
      required = false,
      name,
      includeInactive = false,
    },
    ref,
  ) => {
    const {
      searchTerm,
      results,
      isOpen,
      isLoading,
      selectedEmployee,
      wrapperRef,
      handleSelect,
      handleClear,
      handleInputChange,
    } = useEmployeeSearch({ value, includeInactive });

    const inputClasses = getInputClasses(disabled, error);

    return (
      <div className="w-full" ref={ref || wrapperRef}>
        {label && (
          <label className="mb-1.5 block text-sm font-medium text-gray-700 dark:text-gray-300">
            {label}
            {required && <span className="text-error-400 ml-1">*</span>}
          </label>
        )}

        <div className="relative">
          {selectedEmployee ? (
            <EmployeeSearchInputSelected
              selectedEmployee={selectedEmployee}
              disabled={disabled}
              onClear={() => handleClear(onChange)}
            />
          ) : (
            <div className="relative">
              <input
                type="text"
                name={name}
                value={searchTerm}
                onChange={(e) => handleInputChange(e, onChange)}
                placeholder={placeholder}
                disabled={disabled}
                className={inputClasses}
                autoComplete="off"
              />
              {isLoading && (
                <div className="absolute top-1/2 right-3 -translate-y-1/2">
                  <div className="border-brand-500 h-4 w-4 animate-spin rounded-full border-b-2"></div>
                </div>
              )}
            </div>
          )}

          <EmployeeSearchInputDropdown
            isOpen={isOpen}
            results={results}
            searchTerm={searchTerm}
            isLoading={isLoading}
            onSelect={(emp) => handleSelect(emp, onChange)}
          />
        </div>

        {hint && (
          <p
            className={`mt-1.5 text-xs ${
              error ? "text-error-400" : "text-gray-500 dark:text-gray-400"
            }`}
          >
            {hint}
          </p>
        )}
      </div>
    );
  },
);

EmployeeSearchInput.displayName = "EmployeeSearchInput";

export default EmployeeSearchInput;
