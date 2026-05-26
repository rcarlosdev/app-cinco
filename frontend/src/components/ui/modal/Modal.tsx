"use client";

import React, { useRef } from "react";
import { ModalProps } from "./Modal.types";
import { useModalLogic } from "./Modal.hooks";
import {
  getModalSizeClass,
  getModalAnimationClass,
  combineModalClasses,
} from "./Modal.utils";
import {
  ModalOverlay,
  ModalHeader,
  ModalContent,
  ModalCloseButton,
  ModalActions,
} from "./components";

/**
 * Componente Modal reutilizable con arquitectura modular
 *
 * Features:
 * - Apertura/cierre con transiciones suaves
 * - Soporte para Escape key
 * - Bloqueo de scroll del body
 * - Modales bloqueantes (que no se pueden cerrar fácilmente)
 * - Múltiples tamaños predefinidos
 * - Animaciones personalizables
 * - Accesibilidad mejorada
 *
 * @template Props del modal
 *
 * @example
 * ```tsx
 * const [isOpen, setIsOpen] = useState(false);
 *
 * <Modal
 *   isOpen={isOpen}
 *   onClose={() => setIsOpen(false)}
 *   size="lg"
 * >
 *   <Modal.Header showCloseButton onClose={() => setIsOpen(false)} />
 *   <Modal.Content>
 *     <h2>Contenido</h2>
 *   </Modal.Content>
 *   <Modal.Actions
 *     primaryButton={<Button>Aceptar</Button>}
 *     secondaryButton={<Button>Cancelar</Button>}
 *   />
 * </Modal>
 * ```
 */
const ModalComponent = React.forwardRef<HTMLDivElement, ModalProps>(
  (
    {
      isOpen,
      onClose,
      children,
      className,
      showCloseButton = true,
      isFullscreen = false,
      closeOutside = false,
      size = "md",
      animation = "none",
      title,
      isBlocking = false,
      onBlockingAttempt,
    },
    ref,
  ) => {
    const modalRef = useRef<HTMLDivElement>(null);
    const internalRef =
      (ref as React.MutableRefObject<HTMLDivElement | null>) || modalRef;

    // Lógica integrada del modal
    const { handleContentClick, handleClose } = useModalLogic(
      isOpen,
      onClose,
      isBlocking,
      onBlockingAttempt,
    );

    // No renderizar si no está abierto
    if (!isOpen) {
      return null;
    }

    // Obtener clases combinadas
    const contentClasses = isFullscreen
      ? "w-full h-full"
      : combineModalClasses(size, animation, className);

    // Callback seguro para cerrar (respeta isBlocking)
    const safeClose = handleClose(onClose);

    return (
      <div
        className="modal fixed inset-0 z-99999 flex items-start justify-center overflow-y-auto p-3 sm:items-center sm:p-4"
        role="dialog"
        aria-modal="true"
        aria-labelledby={title}
      >
        {/* Overlay */}
        <ModalOverlay
          show={!isFullscreen}
          closeOutside={closeOutside}
          onClick={safeClose}
        />

        {/* Contenido del modal */}
        <div
          ref={internalRef}
          className={contentClasses}
          onClick={handleContentClick}
        >
          {/* Si showCloseButton, renderizar header con close button automáticamente */}
          {showCloseButton && !isFullscreen && (
            <ModalHeader showCloseButton={true} onClose={safeClose} />
          )}

          {/* Renderizar el contenido (children) - puede incluir Modal.Header, Modal.Content, etc */}
          {children}
        </div>
      </div>
    );
  },
);

ModalComponent.displayName = "Modal";

// Crear interfaz para Modal con sub-componentes
interface ModalComponentType extends React.ForwardRefExoticComponent<
  ModalProps & React.RefAttributes<HTMLDivElement>
> {
  Header: typeof ModalHeader;
  Content: typeof ModalContent;
  CloseButton: typeof ModalCloseButton;
  Actions: typeof ModalActions;
  Overlay: typeof ModalOverlay;
}

// Asignar sub-componentes al componente Modal
export const Modal = ModalComponent as ModalComponentType;
Modal.Header = ModalHeader;
Modal.Content = ModalContent;
Modal.CloseButton = ModalCloseButton;
Modal.Actions = ModalActions;
Modal.Overlay = ModalOverlay;
