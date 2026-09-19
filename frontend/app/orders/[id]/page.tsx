import { OrderInspector } from "@/components/OrderInspector";

export default async function OrderPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return <OrderInspector orderId={id} />;
}
