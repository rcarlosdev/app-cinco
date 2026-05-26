"use client";
import { useEffect, useState } from "react";
import Form from "@/components/form/Form";
import Label from "@/components/form/Label";
import { useRouter } from "next/navigation";
import { EyeCloseIcon, EyeIcon } from "@/icons";
import { useAuthStore } from "@/store/auth.store";
import Button from "@/components/ui/button/Button";
import { Controller, useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { useFormSubmit } from "@/hooks/useFormSubmit";
import Input from "@/components/form/input/InputField";
import { getErrorMessage, ApiErrorType } from "@/lib/errorHandler";
import { loginSchema, LoginFormValues } from "@/schemas/auth.schema";
import { logDevelopmentError } from "@/lib/environment";
import {
  consumeSessionProtectionEvent,
  getSessionProtectionMessage,
} from "@/lib/sessionProtection";
import { toast } from "sonner";

export default function SignInForm() {
  const router = useRouter();
  const login = useAuthStore((state) => state.login);
  const [showPassword, setShowPassword] = useState(false);
  const { submit, isLoading, error } = useFormSubmit<LoginFormValues>();
  const {
    handleSubmit,
    control,
    formState: { errors, isSubmitting },
  } = useForm<LoginFormValues>({
    resolver: zodResolver(loginSchema),
    defaultValues: {
      username: "",
      password: "",
    },
  });

  useEffect(() => {
    const protectionEvent = consumeSessionProtectionEvent();
    if (!protectionEvent) return;

    toast.error(getSessionProtectionMessage(protectionEvent.reason));
  }, []);

  const onSubmit = async (data: LoginFormValues) => {
    try {
      await submit(data, {
        endpoint: "/auth/login",
        onSuccess: (response) => {
          login(response);
          router.replace("/");
        },
        onError: (error) => {
          const normalizedError = {
            type: error?.type ?? ApiErrorType.UNKNOWN,
            status: error?.status ?? 0,
            message: error?.message ?? "Error desconocido",
            detail: error?.detail,
            errors: error?.errors,
          };

          logDevelopmentError("Error al iniciar sesión (raw):", error);
          logDevelopmentError(
            "Error al iniciar sesión (normalizado):",
            normalizedError,
          );
        },
      });
    } catch (error) {
      // El error ya fue manejado por useFormSubmit
      // Solo lo capturamos aquí para prevenir errores no capturados
    }
  };

  const handleForgotPassword = () => {
    // router.push("/forgot-password");
    alert("Para restablecer tu contraseña, por favor contacta a tu líder.");
  };

  return (
    <div className="flex w-full flex-1 flex-col lg:w-1/2">
      <div className="mx-auto flex w-full max-w-md flex-1 flex-col justify-center">
        <div>
          <div className="mb-5 sm:mb-8">
            <h1 className="text-title-sm sm:text-title-md mb-2 font-semibold text-gray-800 dark:text-white/90">
              Bienvenido de nuevo
            </h1>
            <p className="text-sm text-gray-500 dark:text-gray-400">
              Ingresa tus credenciales para acceder a tu cuenta.
            </p>
          </div>
          <div>
            <div className="relative py-3 sm:py-5">
              <div className="absolute inset-0 flex items-center">
                <div className="w-full border-t border-gray-200 dark:border-gray-800"></div>
              </div>
            </div>
            <Form handleSubmit={handleSubmit} onSubmit={onSubmit}>
              <div className="space-y-6">
                <div>
                  <Label htmlFor="username">
                    Nombre de usuario{" "}
                    <span className="text-error-400">*</span>{" "}
                  </Label>
                  <Controller
                    control={control}
                    name="username"
                    render={({ field }) => (
                      <Input
                        {...field}
                        id="username"
                        type="text"
                        inputMode="text"
                        autoComplete="username"
                        placeholder="Ingresa tu nombre de usuario"
                        error={Boolean(errors.username)}
                        hint={errors.username?.message}
                      />
                    )}
                  />
                </div>
                <div>
                  <Label htmlFor="password">
                    Contraseña <span className="text-error-400">*</span>{" "}
                  </Label>
                  <div className="relative">
                    <Controller
                      control={control}
                      name="password"
                      render={({ field }) => (
                        <Input
                          {...field}
                          id="password"
                          type={showPassword ? "text" : "password"}
                          autoComplete="current-password"
                          placeholder="Ingresa tu contraseña"
                          error={Boolean(errors.password)}
                          hint={errors.password?.message}
                        />
                      )}
                    />
                    <span
                      onClick={() => setShowPassword(!showPassword)}
                      className="absolute top-1/2 right-4 z-30 -translate-y-1/2 cursor-pointer"
                    >
                      {showPassword ? (
                        <EyeIcon className="fill-gray-500 dark:fill-gray-400" />
                      ) : (
                        <EyeCloseIcon className="fill-gray-500 dark:fill-gray-400" />
                      )}
                    </span>
                  </div>
                </div>
                <div className="flex items-center justify-center">
                  <span
                    onClick={() => handleForgotPassword()}
                    className="text-brand-500 hover:text-brand-600 dark:text-brand-400 cursor-pointer text-sm"
                  >
                    ¿Olvidaste tu contraseña?
                  </span>
                </div>
                <div>
                  <Button
                    size="sm"
                    type="submit"
                    className="w-full"
                    disabled={isSubmitting || isLoading}
                  >
                    Iniciar sesión
                  </Button>
                </div>
              </div>
            </Form>

            <div className="mt-5">
              {error && (
                <div className="space-y-2">
                  <p className="text-error-600 dark:text-error-400 text-center text-sm font-normal">
                    {getErrorMessage(error)}
                  </p>
                  {error.type === ApiErrorType.VALIDATION && error.errors && (
                    <ul className="text-error-500 space-y-1 text-xs">
                      {Object.entries(error.errors).map(([field, messages]) => (
                        <li key={field}>
                          {Array.isArray(messages) ? messages[0] : messages}
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

