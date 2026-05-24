import Link from "next/link";

export default function BlockedPage() {
  return (
    <div className="min-h-screen flex flex-col items-center justify-center bg-rose-50 p-8 text-center">
      <div className="text-6xl mb-6">🔒</div>
      <h1 className="text-2xl font-bold text-rose-700 mb-3">حساب مسدود شده</h1>
      <p className="text-rose-600 max-w-sm mb-6">
        حساب شما توسط مدیر مسدود شده است. برای اطلاعات بیشتر با پشتیبانی تماس بگیرید.
      </p>
      <Link href="/login" className="text-sm text-rose-500 underline hover:text-rose-700">
        بازگشت به صفحه ورود
      </Link>
    </div>
  );
}
