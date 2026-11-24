import { CompanyHeader } from "@/components/company";

export default function CompanyLayout({ children }: { children: React.ReactNode }) {
  return <><CompanyHeader />{children}</>;
}
