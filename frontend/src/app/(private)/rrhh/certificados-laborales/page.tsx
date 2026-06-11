import { Metadata } from "next";
import CertificadosLaboralesModule from "@/modules/rrhh/certificados/CertificadosLaboralesModule";

export const metadata: Metadata = {
  title: "Certificados Laborales - CINCO SAS",
  description: "Prueba b├ísica para validar la generaci├│n de certificados laborales en PDF.",
};

const CertificadosLaboralesPage = () => {
  return <CertificadosLaboralesModule />;
};

export default CertificadosLaboralesPage;
