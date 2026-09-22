from django import forms

from .models import OnlineOrder, OnlineOrderItem, OnlineOrderStatus, Product


class OnlineOrderForm(forms.ModelForm):
    class Meta:
        model = OnlineOrder
        fields = ("customer_name", "customer_contact", "rm_number", "customer_address", "product", "product_name", "quantity", "note")
        widgets = {"note": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["rm_number"].initial = ""
        self.fields["rm_number"].widget = forms.TextInput(attrs={"placeholder": "c7548"})
        self.fields["rm_number"].help_text = "Contoh: c7548 → JC-7548. Prefix cabang ditambahkan otomatis. Jangan mengetik prefix di field lain."
        self.fields["customer_address"].widget = forms.Textarea(attrs={"rows": 3})
        self.fields["rm_number"].required = True
        self.fields["customer_address"].required = True
        self.fields["product"].queryset = Product.objects.filter(active=True)
        self.fields["product"].required = False
        self.fields["product_name"].required = False
        self.fields["product"].label = "Produk dari katalog"
        self.fields["product_name"].label = "Nama produk manual (jika tidak ada di katalog)"
        self.fields["product_name"].help_text = "Kosongkan bila memilih produk dari dropdown."
        self.fields["product"].label_from_instance = lambda product: (
            f"{product.name} · {product.category}"
            + (f" · {product.ingredient}" if product.ingredient else "")
        )
        self.fields["product"].help_text = "Pilih dari daftar produk; isi nama manual hanya bila belum ada di katalog."

    def clean(self):
        data = super().clean()
        if not data.get("product") and not data.get("product_name"):
            raise forms.ValidationError("Pilih produk atau isi nama produk manual.")
        return data


class OnlineOrderStatusForm(forms.ModelForm):
    class Meta:
        model = OnlineOrder
        fields = ("status", "note")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["status"].choices = OnlineOrderStatus.choices


class OnlineOrderItemForm(forms.ModelForm):
    class Meta:
        model = OnlineOrderItem
        fields = ("product", "product_name", "quantity")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["product"].queryset = Product.objects.filter(active=True)
        self.fields["product"].required = False
        self.fields["product_name"].required = False
        self.fields["product"].label = "Produk dari katalog"
        self.fields["product_name"].label = "Nama produk manual"

    def clean(self):
        data = super().clean()
        if not data.get("product") and not data.get("product_name"):
            raise forms.ValidationError("Pilih produk atau isi nama produk manual.")
        return data
