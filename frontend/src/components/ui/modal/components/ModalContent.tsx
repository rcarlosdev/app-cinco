import { ModalContentProps } from "../Modal.types";

/**
 * Componente que renderiza el contenido del modal
 * Maneja scrolling si el contenido es muy largo
 *
 * @param children - Contenido a renderizar
 * @param scrollable - Si el contenido es scrolleable
 * @param className - Clase CSS adicional
 */
export const ModalContent = ({
  children,
  scrollable = false,
  className,
}: ModalContentProps) => {
  return (
    <div
      className={` ${scrollable ? "max-h-[calc(100vh-8rem)] overflow-y-auto overscroll-contain sm:max-h-[70vh]" : ""} ${className || ""} `}
    >
      {children}
    </div>
  );
};
