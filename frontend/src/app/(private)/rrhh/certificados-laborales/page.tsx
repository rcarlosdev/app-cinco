import { Metadata } from "next";
import CertificadosLaboralesModule from "@/modules/rrhh/certificados/CertificadosLaboralesModule";

export const metadata: Metadata = {
  title: "Certificados Laborales - CINCO SAS",
  description: "Prueba básica para validar la generación de certificados laborales en PDF.",
};

const CertificadosLaboralesPage = () => {
  return <CertificadosLaboralesModule />;
};

export default CertificadosLaboralesPage;
