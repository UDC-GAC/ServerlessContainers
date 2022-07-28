{% macro input_img(name, width='100%', caption="") -%}
	<figure>
      <a href='../img/{{ name }}' target="_blank"><img width={{ width }} class="centered_image" src="../img/{{ name }}"></img></a>
      {% if (caption is defined) and caption %}
          <figcaption>{{ caption }}</figcaption>
      {% endif %}
    </figure>
{%- endmacro %}
