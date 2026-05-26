export const isDevelopmentEnvironment = (): boolean =>
  process.env.NODE_ENV === "development";

export const shouldExposeTechnicalDetails = (): boolean =>
  isDevelopmentEnvironment();

export const logDevelopmentError = (...args: unknown[]): void => {
  if (shouldExposeTechnicalDetails()) {
    console.error(...args);
  }
};

export const logDevelopmentWarning = (...args: unknown[]): void => {
  if (shouldExposeTechnicalDetails()) {
    console.warn(...args);
  }
};
