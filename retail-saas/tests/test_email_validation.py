import pytest
from app.utils.validators import validate_email_address, validate_email_format
from app.schemas.user import UserCreate


class TestEmailValidator:

    def test_valid_emails_pass(self):
        valid_cases = [
            "user@gmail.com",
            "john.doe@example.org",
            "support@retail-os.in",
            "contact@store.co.uk",
            "admin@retailos.canonical",
            "staff+test@company.net",
        ]
        for email in valid_cases:
            assert validate_email_address(email) == email.lower()

    def test_case_insensitivity(self):
        assert validate_email_address("USER@GMAIL.COM") == "user@gmail.com"
        assert validate_email_address("  Rohan@Domain.Org  ") == "rohan@domain.org"

    def test_null_and_empty(self):
        with pytest.raises(ValueError, match="required"):
            validate_email_address(None, required=True)

        assert validate_email_address(None, required=False) is None

        with pytest.raises(ValueError, match="cannot be empty"):
            validate_email_address("   ", required=True)

        assert validate_email_address("   ", required=False) is None

    def test_placeholders_rejected(self):
        for placeholder in ["string", "null", "none", "undefined"]:
            with pytest.raises(ValueError, match="cannot be placeholder"):
                validate_email_address(placeholder)

    def test_max_length_rejected(self):
        long_email = "a" * 250 + "@example.com"
        with pytest.raises(ValueError, match="cannot exceed 254 characters"):
            validate_email_address(long_email)

    def test_missing_or_multiple_at_symbol(self):
        with pytest.raises(ValueError, match="Invalid email address"):
            validate_email_address("plainaddress")

        with pytest.raises(ValueError, match="Invalid email address"):
            validate_email_address("user@domain@extra.com")

    def test_invalid_local_part(self):
        with pytest.raises(ValueError, match="username before @"):
            validate_email_address("@example.com")

        with pytest.raises(ValueError, match="cannot start or end with a dot"):
            validate_email_address(".user@example.com")

        with pytest.raises(ValueError, match="cannot start or end with a dot"):
            validate_email_address("user.@example.com")

        with pytest.raises(ValueError, match="consecutive dots"):
            validate_email_address("user..name@example.com")

        with pytest.raises(ValueError, match="username must not exceed 64 characters"):
            validate_email_address("a" * 65 + "@example.com")

    def test_invalid_domain_structure(self):
        with pytest.raises(ValueError, match="Email must contain a valid domain"):
            validate_email_address("user@")

        with pytest.raises(ValueError, match="valid domain extension"):
            validate_email_address("user@localhost")

        with pytest.raises(ValueError, match="cannot start or end with a dot"):
            validate_email_address("user@.example.com")

        with pytest.raises(ValueError, match="cannot start or end with a dot"):
            validate_email_address("user@example.com.")

        with pytest.raises(ValueError, match="consecutive dots"):
            validate_email_address("user@example..com")

        with pytest.raises(ValueError, match="Invalid email domain label"):
            validate_email_address("user@-example.com")

        with pytest.raises(ValueError, match="Invalid email domain label"):
            validate_email_address("user@example-.com")

    def test_invalid_tld_structure(self):
        with pytest.raises(ValueError, match="must contain only letters"):
            validate_email_address("user@domain.123")

        with pytest.raises(ValueError, match="is too short"):
            validate_email_address("user@domain.c")

    def test_popular_domain_typos_rejected(self):
        typos = [
            ("rohanpawar3333@gmail.comm", "gmail.com"),
            ("user@gmail.con", "gmail.com"),
            ("user@gmail.coom", "gmail.com"),
            ("user@gmail.cm", "gmail.com"),
            ("user@gmail.cpm", "gmail.com"),
            ("user@yahoo.comm", "yahoo.com"),
            ("user@yahoo.con", "yahoo.com"),
            ("user@hotmail.comm", "hotmail.com"),
            ("user@outlook.con", "outlook.com"),
            ("user@icloud.comm", "icloud.com"),
        ]
        for bad_email, suggestion in typos:
            with pytest.raises(ValueError) as exc:
                validate_email_address(bad_email)
            assert suggestion in str(exc.value)

    def test_generic_tld_typos_rejected(self):
        tld_typos = [
            ("user@customcompany.comm", ".com"),
            ("user@customcompany.coom", ".com"),
            ("user@customcompany.con", ".com"),
            ("user@customcompany.cpm", ".com"),
            ("user@customcompany.inn", ".in"),
            ("user@customcompany.orgg", ".org"),
            ("user@customcompany.nett", ".net"),
        ]
        for bad_email, suggestion in tld_typos:
            with pytest.raises(ValueError) as exc:
                validate_email_address(bad_email)
            assert suggestion in str(exc.value)

    def test_pydantic_user_create_rejects_typo_email(self):
        with pytest.raises(ValueError, match="gmail.com"):
            UserCreate(
                email="rohanpawar3333@gmail.comm",
                full_name="Rohan Pawar",
                password="Password123!",
                phone="9876543210",
                role="staff",
            )

    def test_customer_schemas_reject_typo_email(self):
        from app.schemas.customer import CustomerCreate, CustomerUpdate
        with pytest.raises(ValueError, match="gmail.com"):
            CustomerCreate(
                name="Rohan Customer",
                phone="9876543210",
                email="customer@gmail.comm",
            )
        with pytest.raises(ValueError, match="gmail.com"):
            CustomerUpdate(
                email="customer@gmail.comm",
            )

    def test_supplier_schemas_reject_typo_email(self):
        from app.schemas.supplier import SupplierCreate, SupplierUpdate
        with pytest.raises(ValueError, match="gmail.com"):
            SupplierCreate(
                name="Supplier ABC",
                email="supplier@gmail.comm",
            )
        with pytest.raises(ValueError, match="gmail.com"):
            SupplierUpdate(
                email="supplier@gmail.comm",
            )

    def test_store_schemas_reject_typo_email(self):
        from app.schemas.store import StoreCreate, StoreUpdate
        with pytest.raises(ValueError, match="gmail.com"):
            StoreCreate(
                name="Main Store",
                code="MAIN01",
                address="123 MG Road",
                city="Pune",
                state="Maharashtra",
                pincode="411001",
                phone="9876543210",
                email="store@gmail.comm",
            )
        with pytest.raises(ValueError, match="gmail.com"):
            StoreUpdate(
                email="store@gmail.comm",
            )

    def test_super_admin_schemas_reject_typo_email(self):
        from app.schemas.super_admin import SuperAdminCreate, SuperAdminLogin, SuperAdminStoreOwnerCreate
        with pytest.raises(ValueError, match="gmail.com"):
            SuperAdminCreate(
                email="superadmin@gmail.comm",
                full_name="Super Admin",
                password="Password123!",
            )
        with pytest.raises(ValueError, match="gmail.com"):
            SuperAdminLogin(
                email="superadmin@gmail.comm",
                password="Password123!",
            )
        with pytest.raises(ValueError, match="gmail.com"):
            SuperAdminStoreOwnerCreate(
                store_name="Demo Store",
                owner_name="Demo Owner",
                owner_email="owner@gmail.comm",
                password="Password123!",
            )

    def test_document_setting_schemas_reject_typo_email(self):
        from app.schemas.document_setting import DocumentSettingCreate, DocumentSettingUpdate
        with pytest.raises(ValueError, match="gmail.com"):
            DocumentSettingCreate(
                business_name="Demo Mart",
                email="billing@gmail.comm",
            )
        with pytest.raises(ValueError, match="gmail.com"):
            DocumentSettingUpdate(
                email="billing@gmail.comm",
            )


class TestGSTINValidator:

    def test_valid_gstin(self):
        from app.utils.validators import validate_gstin_number
        assert validate_gstin_number("27AAAAA0000A1Z5") == "27AAAAA0000A1Z5"
        assert validate_gstin_number("27ABCDE1234F1Z5") == "27ABCDE1234F1Z5"
        assert validate_gstin_number("  29AABCT1332L1Z1  ") == "29AABCT1332L1Z1"

    def test_invalid_gstin(self):
        from app.utils.validators import validate_gstin_number
        with pytest.raises(ValueError, match="15 characters"):
            validate_gstin_number("27AAAAA0000A1Z")

        with pytest.raises(ValueError, match="Invalid GSTIN format"):
            validate_gstin_number("INVALIDGSTIN123")

        with pytest.raises(ValueError, match="state code"):
            validate_gstin_number("00AAAAA0000A1Z5")

        with pytest.raises(ValueError, match="cannot be placeholder"):
            validate_gstin_number("string")


class TestWebsiteValidator:

    def test_valid_websites(self):
        from app.utils.validators import validate_website_url
        assert validate_website_url("https://retail-os.in") == "https://retail-os.in"
        assert validate_website_url("http://store.co.in") == "http://store.co.in"
        assert validate_website_url("www.mystore.com") == "www.mystore.com"
        assert validate_website_url("retailos.in") == "retailos.in"

    def test_invalid_websites(self):
        from app.utils.validators import validate_website_url
        with pytest.raises(ValueError, match="Invalid website format"):
            validate_website_url("not-a-website")

        with pytest.raises(ValueError, match="cannot be placeholder"):
            validate_website_url("string")


class TestStoreOwnerPhoneAndPincodeValidation:

    def test_store_owner_phone_validation(self):
        from app.schemas.super_admin import SuperAdminStoreOwnerCreate
        with pytest.raises(ValueError, match="mobile number"):
            SuperAdminStoreOwnerCreate(
                store_name="Demo Store",
                owner_name="Demo Owner",
                owner_email="owner@gmail.com",
                password="Password123!",
                owner_phone="12345",
            )

        # Valid phone normalized
        schema = SuperAdminStoreOwnerCreate(
            store_name="Demo Store",
            owner_name="Demo Owner",
            owner_email="owner@gmail.com",
            password="Password123!",
            owner_phone="+91 9876543210",
        )
        assert schema.owner_phone == "9876543210"

    def test_store_owner_pincode_validation(self):
        from app.schemas.super_admin import SuperAdminStoreOwnerCreate
        with pytest.raises(ValueError, match="Pincode must contain exactly 6 digits"):
            SuperAdminStoreOwnerCreate(
                store_name="Demo Store",
                owner_name="Demo Owner",
                owner_email="owner@gmail.com",
                password="Password123!",
                pincode="123",
            )

        with pytest.raises(ValueError, match="First digit of Indian pincode cannot be 0"):
            SuperAdminStoreOwnerCreate(
                store_name="Demo Store",
                owner_name="Demo Owner",
                owner_email="owner@gmail.com",
                password="Password123!",
                pincode="012345",
            )

        # Valid pincode
        schema = SuperAdminStoreOwnerCreate(
            store_name="Demo Store",
            owner_name="Demo Owner",
            owner_email="owner@gmail.com",
            password="Password123!",
            pincode="411001",
        )
        assert schema.pincode == "411001"

