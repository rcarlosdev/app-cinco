export const getInputClasses = (disabled: boolean, error: boolean): string => {
  let classes = `h-8 w-full rounded-lg border appearance-none px-2 py-0.5 text-sm shadow-theme-xs placeholder:text-gray-400 focus:outline-hidden focus:ring-3 dark:bg-gray-900 dark:text-white/90 dark:placeholder:text-white/30`;

  if (disabled) {
    classes += ` text-gray-500 border-gray-300 cursor-not-allowed dark:bg-gray-800 dark:text-gray-400 dark:border-gray-700`;
  } else if (error) {
    classes += ` text-error-800 border-error-500 focus:ring-3 focus:ring-error-500/10 dark:text-error-400 dark:border-error-500`;
  } else {
    classes += ` bg-transparent text-gray-800 border-gray-300 focus:border-brand-300 focus:ring-3 focus:ring-brand-500/10 dark:border-gray-700 dark:bg-gray-900 dark:text-white/90 dark:focus:border-brand-800`;
  }

  return classes;
};

export const EMPLOYEE_SEARCH_CONFIG = {
  debounceDelay: 300,
  minSearchLength: 2,
  maxDropdownHeight: "max-h-60 sm:max-h-80",
} as const;
