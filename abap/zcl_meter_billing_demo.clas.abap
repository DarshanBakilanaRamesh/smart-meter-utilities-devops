CLASS zcl_meter_billing_demo DEFINITION
  PUBLIC
  FINAL
  CREATE PUBLIC.

  PUBLIC SECTION.
    INTERFACES if_oo_adt_classrun.
ENDCLASS.


CLASS zcl_meter_billing_demo IMPLEMENTATION.
  METHOD if_oo_adt_classrun~main.
    DATA(service) = NEW zcl_meter_billing( ).
    DATA(result) = service->calculate_bill(
      iv_previous_reading = '12450'
      iv_current_reading  = '12820' ).

    out->write( |Consumption: { result-consumption_kwh } kWh| ).
    out->write( |Energy amount: { result-energy_amount } EUR| ).
    out->write( |VAT: { result-vat_amount } EUR| ).
    out->write( |Total: { result-total_amount } EUR| ).
    out->write( |Status: { result-status }| ).
  ENDMETHOD.
ENDCLASS.
