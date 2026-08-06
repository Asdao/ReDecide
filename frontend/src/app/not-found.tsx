import type { Metadata } from "next";
import Link from "next/link";
import { ProductHeader } from "@/components/ProductHeader";

export const metadata: Metadata = {
  title: "404",
};

export default function NotFound() {
  return (
    <main className="shell not-found-shell">
      <ProductHeader brandHref="/" label="Page not found" />
      <section className="not-found-content" id="main-content" aria-labelledby="not-found-title">
        <div className="not-found-copy">
          <h1 id="not-found-title">404</h1>
          <p>The page you&apos;re looking for doesn&apos;t exist.</p>
          <Link className="primary not-found-home" href="/">
            Return home
          </Link>
        </div>
      </section>
    </main>
  );
}
