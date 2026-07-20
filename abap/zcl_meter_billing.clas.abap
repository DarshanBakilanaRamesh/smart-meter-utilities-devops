CLASS zcl_meter_billing DEFINITION
  PUBLIC
  FINAL
  CREATE PUBLIC.

  PUBLIC SECTION.
    TYPES: BEGIN OF ty_bill_result,
             previous_reading TYPE decfloat34,
             current_reading  TYPE decfloat34,
             consumption_kwh  TYPE decfloat34,
             energy_amount    TYPE decfloat34,
             basic_charge     TYPE decfloat34,
             vat_amount       TYPE decfloat34,
             total_amount     TYPE decfloat34,
             status           TYPE string,
           END OF ty_bill_result.

    TYPES: BEGIN OF ty_validation_result,
             valid   TYPE abap_bool,
             message TYPE string,
           END OF ty_validation_result.

    METHODS validate_reading
      IMPORTING
        iv_previous_reading TYPE decfloat34
        iv_current_reading  TYPE decfloat34
      RETURNING
        VALUE(rs_result)    TYPE ty_validation_result.

    METHODS calculate_bill
      IMPORTING
        iv_previous_reading TYPE decfloat34
        iv_current_reading  TYPE decfloat34
        iv_price_per_kwh    TYPE decfloat34 DEFAULT '0.35'
        iv_basic_charge     TYPE decfloat34 DEFAULT '12.00'
        iv_vat_rate         TYPE decfloat34 DEFAULT '0.19'
      RETURNING
        VALUE(rs_bill)      TYPE ty_bill_result
      RAISING
        cx_sy_illegal_argument.
ENDCLASS.


CLASS zcl_meter_billing IMPLEMENTATION.
  METHOD validate_reading.
    IF iv_previous_reading < 0 OR iv_current_reading < 0.
      rs_result-valid = abap_false.
      rs_result-message = 'Readings cannot be negative'.
      RETURN.
    ENDIF.

    IF iv_current_reading < iv_previous_reading.
      rs_result-valid = abap_false.
      rs_result-message = 'Current reading cannot be lower than previous reading'.
      RETURN.
    ENDIF.

    rs_result-valid = abap_true.
    rs_result-message = 'Reading is valid'.
  ENDMETHOD.

  METHOD calculate_bill.
    DATA(ls_validation) = validate_reading(
      iv_previous_reading = iv_previous_reading
      iv_current_reading  = iv_current_reading ).

    IF ls_validation-valid = abap_false.
      RAISE EXCEPTION TYPE cx_sy_illegal_argument
        EXPORTING
          textid = cx_sy_illegal_argument=>illegal_argument.
    ENDIF.

    rs_bill-previous_reading = iv_previous_reading.
    rs_bill-current_reading = iv_current_reading.
    rs_bill-consumption_kwh = iv_current_reading - iv_previous_reading.
    rs_bill-energy_amount = rs_bill-consumption_kwh * iv_price_per_kwh.
    rs_bill-basic_charge = iv_basic_charge.
    rs_bill-vat_amount =
      ( rs_bill-energy_amount + rs_bill-basic_charge ) * iv_vat_rate.
    rs_bill-total_amount =
      rs_bill-energy_amount + rs_bill-basic_charge + rs_bill-vat_amount.
    rs_bill-status = 'CREATED'.
  ENDMETHOD.
ENDCLASS.
