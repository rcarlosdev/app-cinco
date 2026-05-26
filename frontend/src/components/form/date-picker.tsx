import { useEffect, useState } from "react";
import flatpickr from "flatpickr";
import "flatpickr/dist/flatpickr.css";
import Label from "./Label";
import { CalenderIcon } from "../../icons";
import Hook = flatpickr.Options.Hook;
import { DateOption } from "flatpickr/dist/types/options";

const DEFAULT_YEAR_RANGE = {
  from: new Date().getFullYear() - 10,
  to: new Date().getFullYear() + 10,
};

type PropsType = {
  id: string;
  mode?: "single" | "multiple" | "range" | "time";
  onChange?: Hook | Hook[];
  defaultDate?: DateOption;
  label?: string;
  placeholder?: string;
  hint?: string;
  error?: boolean;
  success?: boolean;
  options?: Partial<flatpickr.Options.Options>;
  yearRange?: {
    from: number;
    to: number;
  };
};

const normalizeYearRange = (
  range?: PropsType["yearRange"],
): { from: number; to: number } => {
  const from = range?.from ?? DEFAULT_YEAR_RANGE.from;
  const to = range?.to ?? DEFAULT_YEAR_RANGE.to;

  return from <= to ? { from, to } : { from: to, to: from };
};

const syncYearSelect = (
  instance: flatpickr.Instance,
  yearSelect: HTMLSelectElement | null,
) => {
  if (!yearSelect) return;
  yearSelect.value = String(instance.currentYear);
};

const getFirstDateOption = (value?: DateOption): Date | null => {
  if (!value) return null;

  if (value instanceof Date) {
    return Number.isNaN(value.getTime()) ? null : value;
  }

  if (Array.isArray(value)) {
    for (const item of value) {
      const parsed = getFirstDateOption(item);
      if (parsed) return parsed;
    }
    return null;
  }

  if (typeof value === "number") {
    const parsed = new Date(value);
    return Number.isNaN(parsed.getTime()) ? null : parsed;
  }

  if (typeof value === "string") {
    const plainDateMatch = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
    if (plainDateMatch) {
      const [, year, month, day] = plainDateMatch;
      return new Date(Number(year), Number(month) - 1, Number(day), 12);
    }

    const parsed = new Date(value);
    return Number.isNaN(parsed.getTime()) ? null : parsed;
  }

  return null;
};

const formatInputDateValue = (value?: DateOption): string => {
  const date = getFirstDateOption(value);
  if (!date) return "";

  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
};

const triggerOnChangeHooks = (
  hooks: Hook | Hook[] | undefined,
  selectedDates: Date[],
  dateStr: string,
) => {
  if (!hooks) return;

  const hookList = Array.isArray(hooks) ? hooks : [hooks];
  for (const hook of hookList) {
    hook(selectedDates, dateStr, {} as flatpickr.Instance);
  }
};

const mountActionBar = (instance: flatpickr.Instance) => {
  const calendarContainer = instance.calendarContainer;

  if (
    !calendarContainer ||
    calendarContainer.querySelector(".flatpickr-action-bar")
  ) {
    return;
  }

  const actionBar = document.createElement("div");
  actionBar.className = "flatpickr-action-bar";

  const todayButton = document.createElement("button");
  todayButton.type = "button";
  todayButton.className = "flatpickr-action-button";
  todayButton.textContent = "Hoy";
  todayButton.addEventListener("click", () => {
    instance.setDate(new Date(), true);
    instance.jumpToDate(new Date());
    instance.redraw();
  });

  const clearButton = document.createElement("button");
  clearButton.type = "button";
  clearButton.className = "flatpickr-action-button flatpickr-action-button-secondary";
  clearButton.textContent = "Limpiar";
  clearButton.addEventListener("click", () => {
    instance.clear(true);
  });

  actionBar.append(todayButton, clearButton);
  calendarContainer.append(actionBar);
};

const mountYearSelect = (
  instance: flatpickr.Instance,
  range: { from: number; to: number },
) => {
  const calendarContainer = instance.calendarContainer;
  const currentMonth = calendarContainer?.querySelector<HTMLElement>(".cur-month");
  const currentYearWrapper =
    calendarContainer?.querySelector<HTMLElement>(".numInputWrapper");

  if (
    !currentMonth ||
    !currentYearWrapper ||
    currentYearWrapper.dataset.enhancedYear === "true"
  ) {
    return;
  }

  const yearSelect = document.createElement("select");
  yearSelect.className = "flatpickr-year-select";
  yearSelect.setAttribute("aria-label", "Seleccionar anio");

  for (let year = range.from; year <= range.to; year += 1) {
    const option = document.createElement("option");
    option.value = String(year);
    option.textContent = String(year);
    yearSelect.append(option);
  }

  syncYearSelect(instance, yearSelect);

  yearSelect.addEventListener("change", (event) => {
    const target = event.target as HTMLSelectElement;
    instance.changeYear(Number(target.value));
    instance.redraw();
  });

  currentYearWrapper.dataset.enhancedYear = "true";
  currentYearWrapper.innerHTML = "";
  currentYearWrapper.append(yearSelect);

  currentYearWrapper.style.display = "inline-flex";
  currentYearWrapper.style.alignItems = "center";
  currentYearWrapper.style.justifyContent = "center";

  instance.config.onYearChange.push(() => {
    syncYearSelect(instance, yearSelect);
  });

  currentMonth.classList.add("flatpickr-month-select");
};

export default function DatePicker({
  id,
  mode,
  onChange,
  label,
  defaultDate,
  placeholder,
  hint,
  error,
  success,
  options = {},
  yearRange,
}: PropsType) {
  const [isMobile, setIsMobile] = useState(false);

  useEffect(() => {
    if (typeof window === "undefined") return;

    const mediaQuery = window.matchMedia("(max-width: 767px)");
    const syncViewport = () => setIsMobile(mediaQuery.matches);

    syncViewport();
    mediaQuery.addEventListener("change", syncViewport);

    return () => mediaQuery.removeEventListener("change", syncViewport);
  }, []);

  useEffect(() => {
    if (typeof window === "undefined" || isMobile) return;

    const normalizedYearRange = normalizeYearRange(yearRange);
    const mergedOnReady = [
      (
        _selectedDates: Date[],
        _dateStr: string,
        instance: flatpickr.Instance,
      ) => {
        mountYearSelect(instance, normalizedYearRange);
        mountActionBar(instance);
      },
      ...(Array.isArray(options.onReady)
        ? options.onReady
        : options.onReady
          ? [options.onReady]
          : []),
    ];
    const mergedOnOpen = [
      (
        _selectedDates: Date[],
        _dateStr: string,
        instance: flatpickr.Instance,
      ) => {
        mountYearSelect(instance, normalizedYearRange);
        mountActionBar(instance);
      },
      ...(Array.isArray(options.onOpen)
        ? options.onOpen
        : options.onOpen
          ? [options.onOpen]
          : []),
    ];
    const mergedOnMonthChange = [
      (
        _selectedDates: Date[],
        _dateStr: string,
        instance: flatpickr.Instance,
      ) => {
        mountYearSelect(instance, normalizedYearRange);
        mountActionBar(instance);
      },
      ...(Array.isArray(options.onMonthChange)
        ? options.onMonthChange
        : options.onMonthChange
          ? [options.onMonthChange]
          : []),
    ];

    const flatPickrInstance = flatpickr(`#${id}`, {
      ...options,
      mode: mode || "single",
      // monthSelectorType: "static",
      // dateFormat: "Y-m-d",
      defaultDate,
      onChange,
      onReady: mergedOnReady,
      onOpen: mergedOnOpen,
      onMonthChange: mergedOnMonthChange,
      disableMobile: false,
      // altInput: true,
      locale: {
        firstDayOfWeek: 1, // Lunes como primer día de la semana
        weekdays: {
          shorthand: ["Dom", "Lun", "Mar", "Mié", "Jue", "Vie", "Sáb"],
          longhand: [
            "Domingo",
            "Lunes",
            "Martes",
            "Miércoles",
            "Jueves",
            "Viernes",
            "Sábado",
          ],
        },
        months: {
          shorthand: [
            "Ene",
            "Feb",
            "Mar",
            "Abr",
            "May",
            "Jun",
            "Jul",
            "Ago",
            "Sep",
            "Oct",
            "Nov",
            "Dic",
          ],
          longhand: [
            "Enero",
            "Febrero",
            "Marzo",
            "Abril",
            "Mayo",
            "Junio",
            "Julio",
            "Agosto",
            "Septiembre",
            "Octubre",
            "Noviembre",
            "Diciembre",
          ],
        },
      },
      appendTo: document.body, // ✅ aquí sí
    });

    return () => {
      if (!Array.isArray(flatPickrInstance)) {
        flatPickrInstance.destroy();
      }
    };
  }, [mode, onChange, id, defaultDate, options, yearRange, isMobile]);

  const mobileValue = formatInputDateValue(defaultDate);

  if (isMobile) {
    return (
      <div key={`${id}-mobile`}>
        {label && <Label htmlFor={id}>{label}</Label>}

        <div className="relative">
          <input
            key={`${id}-mobile-input`}
            id={id}
            type="date"
            value={mobileValue}
            onChange={(event) => {
              const value = event.target.value;
              const selectedDate = value
                ? new Date(
                    Number(value.slice(0, 4)),
                    Number(value.slice(5, 7)) - 1,
                    Number(value.slice(8, 10)),
                    12,
                  )
                : null;

              triggerOnChangeHooks(
                onChange,
                selectedDate ? [selectedDate] : [],
                value,
              );
            }}
            className={`shadow-theme-xs focus:border-brand-300 focus:ring-brand-500/20 dark:focus:border-brand-800 h-10 w-full appearance-none rounded-lg border border-gray-300 bg-transparent px-3 py-2 text-sm text-gray-800 focus:ring-3 focus:outline-hidden dark:border-gray-700 dark:bg-gray-900 dark:text-white/90 ${error ? "border-red-400 focus:border-red-400 focus:ring-red-400/20" : ""}`}
            aria-invalid={error ? "true" : "false"}
          />
          {hint && (
            <p
              className={`mt-1.5 text-xs ${
                error
                  ? "text-error-400"
                  : success
                    ? "text-success-500"
                    : "text-gray-500"
              }`}
            >
              {hint}
            </p>
          )}
        </div>
      </div>
    );
  }

  return (
    <div key={`${id}-desktop`}>
      {label && <Label htmlFor={id}>{label}</Label>}

      <div className="relative">
        <input
          key={`${id}-desktop-input`}
          id={id}
          placeholder={placeholder}
          defaultValue={mobileValue}
          className={`shadow-theme-xs focus:border-brand-300 focus:ring-brand-500/20 dark:focus:border-brand-800 h-8 w-full appearance-none rounded-lg border border-gray-300 bg-transparent px-2 py-0.5 text-sm text-gray-800 placeholder:text-gray-400 focus:ring-3 focus:outline-hidden dark:border-gray-700 dark:bg-gray-900 dark:text-white/90 dark:placeholder:text-white/30 ${error ? "border-red-400 focus:border-red-400 focus:ring-red-400/20" : ""}`}
          aria-invalid={error ? "true" : "false"}
        />
        {hint && (
          <p
            className={`mt-1.5 text-xs ${
              error
                ? "text-error-400"
                : success
                  ? "text-success-500"
                  : "text-gray-500"
            }`}
          >
            {hint}
          </p>
        )}

        <span className="pointer-events-none absolute top-1/2 right-3 -translate-y-1/2 text-gray-500 dark:text-gray-400">
          <CalenderIcon className="size-6" />
        </span>
      </div>
    </div>
  );
}
