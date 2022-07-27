from marshmallow import Schema, fields
from marshmallow.validate import OneOf

CURRENCIES = ('RUB', 'USD', 'EUR', 'GBP')


class PayerDataSchema(Schema):
    FirstName = fields.String()
    LastName = fields.String()
    MiddleName = fields.String()
    Birth = fields.String()
    Address = fields.String()
    Street = fields.String()
    City = fields.String()
    Country = fields.String()
    Phone = fields.String()
    Postcode = fields.String()


class ChargeRequestSchema(Schema):
    Amount = fields.Integer(required=True)
    Currency = fields.String(validate=OneOf(CURRENCIES))
    InvoiceId = fields.String()
    IpAddress = fields.IP()
    Description = fields.String()
    AccountId = fields.String()
    Name = fields.String()
    CardCryptogramPacket = fields.String(required=True)
    Payer = fields.Nested(PayerDataSchema())
